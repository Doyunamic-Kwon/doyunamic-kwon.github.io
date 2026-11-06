"""Render published reviews using their relative Obsidian folder structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import string
import unicodedata


class FolderError(ValueError):
    """A review folder or sidebar entry cannot be used safely."""


@dataclass(frozen=True)
class TreeEntry:
    folders: tuple[str, ...]
    label: str
    href: str


def _name(value: str, *, folder: bool = False) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise FolderError("폴더와 문서 이름을 확인하세요.")
    if any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
        raise FolderError("폴더와 문서 이름에는 제어문자를 사용할 수 없습니다.")
    if folder and "/" in value:
        raise FolderError("폴더 이름 한 항목에 경로 구분자를 넣을 수 없습니다.")
    return value


def _literal(value: str) -> str:
    # HTML entities stay intact; Markdown punctuation is displayed literally.
    punctuation = set(string.punctuation) - {"&", ";", "<", ">"}
    return "".join("\\" + char if char in punctuation else char for char in escape(value, quote=False))


def _sort_name(value: str) -> tuple[str, str, str]:
    normalized = unicodedata.normalize("NFC", value)
    return normalized.casefold(), normalized, value


@dataclass
class _Node:
    folders: dict[str, _Node] = field(default_factory=dict)
    documents: list[TreeEntry] = field(default_factory=list)


def render_tree(config_text: str, entries: list[TreeEntry]) -> str:
    """Replace only the marked sidebar block, merging common parent folders."""
    if not isinstance(config_text, str):
        raise FolderError("웹사이트 설정을 텍스트로 읽지 못했습니다.")
    lines = config_text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines)
              if line.rstrip("\r\n").rstrip(" \t") == "      # BLOG-TREE-START"]
    ends = [index for index, line in enumerate(lines)
            if line.rstrip("\r\n").rstrip(" \t") == "      # BLOG-TREE-END"]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise FolderError("_quarto.yml에서 BLOG-TREE-START/END 영역을 확인하세요.")
    root = _Node()
    seen: set[TreeEntry] = set()
    for entry in entries:
        if not isinstance(entry, TreeEntry) or not isinstance(entry.folders, tuple):
            raise FolderError("리뷰의 상대 폴더 정보를 확인하세요.")
        for folder in entry.folders:
            _name(folder, folder=True)
        _name(entry.label)
        if not isinstance(entry.href, str) or not re.fullmatch(r"/posts/[a-z0-9]+(?:-[a-z0-9]+)*/", entry.href):
            raise FolderError("리뷰 주소는 /posts/소문자-주소/ 형식이어야 합니다.")
        if entry in seen:
            continue
        seen.add(entry)
        parent = root
        for folder in entry.folders:
            parent = parent.folders.setdefault(folder, _Node())
        parent.documents.append(entry)

    block: list[str] = []

    def render_node(node: _Node, indent: int) -> None:
        prefix = " " * indent
        for folder in sorted(node.folders, key=_sort_name):
            block.extend([
                f"{prefix}- section: {json.dumps(_literal(folder), ensure_ascii=False)}",
                f"{prefix}  contents:",
            ])
            render_node(node.folders[folder], indent + 4)
        for entry in sorted(node.documents, key=lambda document: (_sort_name(document.label), document.href)):
            block.extend([
                f"{prefix}- text: {json.dumps(_literal(entry.label), ensure_ascii=False)}",
                f"{prefix}  href: {json.dumps(entry.href)}",
            ])

    render_node(root, 6)
    newline = "\r\n" if lines[starts[0]].endswith("\r\n") else "\n"
    replacement = "".join(line + newline for line in block)
    return "".join(lines[:starts[0] + 1]) + replacement + "".join(lines[ends[0]:])


def resolve_review_folder(root: Path, relative: str) -> Path:
    """Validate a relative folder without creating it or following outside links."""
    if not isinstance(relative, str) or any(unicodedata.category(char) in {"Cc", "Cs"} for char in relative):
        raise FolderError("저장 폴더의 상대 경로를 확인하세요.")
    if PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).is_absolute():
        raise FolderError("저장 폴더는 Reviews 안의 상대 경로로 지정하세요.")
    parts = PurePosixPath(relative).parts
    for part in parts:
        if part == ".." or part.startswith("."):
            raise FolderError("상위 폴더나 숨김 폴더는 리뷰 저장 위치로 사용할 수 없습니다.")
        _name(part, folder=True)
    try:
        root = Path(root).expanduser()
        if root.is_symlink() or (root.exists() and not root.is_dir()):
            raise FolderError("Reviews 폴더의 경로를 확인하세요.")
        resolved_root = root.resolve()
        candidate = root.joinpath(*parts)
        resolved = candidate.resolve()
        resolved_parts = resolved.relative_to(resolved_root).parts
        if any(part.startswith(".") for part in resolved_parts):
            raise FolderError("숨김 폴더는 리뷰 저장 위치로 사용할 수 없습니다.")
        current = root
        for part in parts:
            current /= part
            if current.exists() and not current.is_dir():
                raise FolderError("저장 폴더 경로에 문서 파일이 있습니다.")
        return candidate
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, FolderError):
            raise
        raise FolderError("저장 폴더가 Reviews 밖으로 연결되거나 접근할 수 없습니다.") from None


def list_review_folders(root: Path) -> list[str]:
    """List visible relative folders, with '.' as the Reviews-root choice."""
    root = resolve_review_folder(root, "")
    folders = ["."]
    if not root.exists():
        return folders

    def fail(_error: OSError) -> None:
        raise FolderError("Reviews의 폴더 목록을 읽지 못했습니다.") from None

    try:
        for current, directories, _files in os.walk(root, topdown=True, followlinks=False, onerror=fail):
            directories[:] = sorted(
                (name for name in directories if not name.startswith(".")
                 and not (Path(current) / name).is_symlink()),
                key=_sort_name,
            )
            for directory in directories:
                _name(directory, folder=True)
                folders.append((Path(current) / directory).relative_to(root).as_posix())
    except OSError:
        raise FolderError("Reviews의 폴더 목록을 읽지 못했습니다.") from None
    return [".", *sorted(folders[1:], key=lambda value: tuple(_sort_name(part) for part in PurePosixPath(value).parts))]
