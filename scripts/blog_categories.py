"""Read the user's sidebar categories from a private Markdown document."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import quote


CATEGORY_FILE = "Blog/블로그 분류.md"
MAX_CATEGORY_LENGTH = 80
_START = "      # BLOG-CATEGORIES-START"
_END = "      # BLOG-CATEGORIES-END"
_DEFAULT_NAMES = ("LLM", "RAG", "Agent")
_DEFAULT_DOCUMENT = """# 블로그 분류

체크한 분류는 블로그 왼쪽 메뉴에 표시됩니다. 체크를 해제해도 기존 글은 삭제되지 않습니다.

목록을 수정한 뒤 ‘블로그 게시하기’를 실행하면 사이트에 반영됩니다.

분류 항목의 순서를 바꾸면 메뉴 순서도 바뀝니다. 새 항목을 추가하면 새 분류가 생깁니다.

분류 이름을 바꿀 때에는 기존 리뷰의 categories도 같은 이름으로 수정하세요.

이름은 80자 이하의 일반 텍스트로 작성하세요. 아래 목록 밖의 설명 문단은 메뉴에 표시되지 않습니다.

- [x] LLM
- [x] RAG
- [x] Agent
"""


class CategoryError(ValueError):
    """A category document or name needs attention."""


@dataclass(frozen=True)
class Category:
    name: str
    selected: bool = True


def validate_category(name: str) -> str:
    if not isinstance(name, str):
        raise CategoryError("분류 이름은 일반 텍스트로 입력하세요.")
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in name):
        raise CategoryError("분류 이름에는 줄바꿈이나 제어문자를 사용할 수 없습니다.")
    name = unicodedata.normalize("NFC", unescape(name))
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in name):
        raise CategoryError("분류 이름에는 줄바꿈이나 제어문자를 사용할 수 없습니다.")
    name = name.strip()
    if not name:
        raise CategoryError("분류 이름을 입력하세요.")
    if len(name) > MAX_CATEGORY_LENGTH:
        raise CategoryError(f"분류 이름은 {MAX_CATEGORY_LENGTH}자 이하로 입력하세요.")
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in name):
        raise CategoryError("분류 이름에는 줄바꿈이나 제어문자를 사용할 수 없습니다.")
    if (re.search(r"[A-Za-z][A-Za-z0-9+.-]*://", name)
            or re.search(r"\b(?:file|obsidian|zotero|vscode|javascript|data|x-apple-[a-z-]+)\s*:", name, re.I)
            or name.startswith(("/", "\\", "~/", "~\\"))
            or re.search(r"(?:^|\s)[A-Za-z]:[/\\]", name)):
        raise CategoryError("분류 이름에는 파일 경로나 링크 대신 일반 텍스트를 입력하세요.")
    if (re.search(r"[<>{}\\`*\[\]]|%%", name)
            or re.search(r"(?:^_|_$|__)", name)
            or re.search(r"(?<!\w)_[^_]+_(?!\w)|~~", name)
            or re.match(r"#+\s", name)):
        raise CategoryError("분류 이름에는 HTML이나 Markdown 서식 대신 일반 텍스트를 입력하세요.")
    return name


def _category_path(vault: Path) -> Path:
    try:
        root = Path(vault).expanduser()
        resolved_root = root.resolve()
        if root.exists() and not root.is_dir():
            raise CategoryError("Obsidian 보관함 폴더를 확인하세요.")
        path = root / CATEGORY_FILE
        path.resolve().relative_to(resolved_root)
        if path.exists() and not path.is_file():
            raise CategoryError("블로그 분류 문서 경로에 파일이 아닌 항목이 있습니다.")
        return path
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, CategoryError):
            raise
        raise CategoryError("분류 문서 경로가 보관함 밖으로 연결되거나 접근할 수 없습니다.") from None


def _read_document(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", newline="") as document:
            return document.read()
    except (OSError, UnicodeError):
        raise CategoryError("블로그 분류 문서를 UTF-8 텍스트로 읽지 못했습니다.") from None


def _parse_document(text: str) -> list[Category]:
    categories: list[Category] = []
    seen: set[str] = set()
    fence: tuple[str, int] | None = None
    in_comment = False
    in_private = False
    for line_number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= fence[1] and not marker.group(2).strip():
                fence = None
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if marker and not in_private:
            fence = (marker.group(1)[0], len(marker.group(1)))
            continue
        visible = []
        parts = line.split("%%")
        for index, part in enumerate(parts):
            if not in_private:
                visible.append(part)
            if index < len(parts) - 1:
                in_private = not in_private
        line = "".join(visible)
        if line.lstrip().startswith("<!--"):
            in_comment = "-->" not in line
            continue
        if re.fullmatch(r"\s*(?:-\s*){3,}", line):
            continue
        bullet = re.fullmatch(r" {0,3}-(?:[ \t]+(.*))?", line)
        if not bullet:
            continue
        value = bullet.group(1) or ""
        checkbox = re.fullmatch(r"\[([xX ])\](?:[ \t]+(.*))?", value)
        selected = True
        if checkbox:
            selected = checkbox.group(1).casefold() == "x"
            value = checkbox.group(2) or ""
        try:
            name = validate_category(value)
        except CategoryError as error:
            raise CategoryError(f"분류 문서 {line_number}행: {error}") from None
        if name.casefold() in seen:
            raise CategoryError(f"분류 문서 {line_number}행에 같은 이름의 분류가 중복되어 있습니다.")
        seen.add(name.casefold())
        categories.append(Category(name, selected))
    if fence or in_comment or in_private:
        raise CategoryError("분류 문서의 코드 블록이나 주석을 닫은 뒤 다시 실행하세요.")
    return categories


def ensure_categories(vault: Path) -> Path:
    """Create the default document only if it does not already exist."""
    path = _category_path(vault)
    if path.exists():
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path = _category_path(vault)
        with path.open("x", encoding="utf-8", newline="") as document:
            document.write(_DEFAULT_DOCUMENT)
    except FileExistsError:
        pass
    except OSError:
        raise CategoryError("블로그 분류 문서를 만들지 못했습니다. 보관함 경로와 권한을 확인하세요.") from None
    return path


def read_categories(vault: Path) -> list[Category]:
    """Return ordered categories; a missing file uses the initial defaults."""
    path = _category_path(vault)
    if not path.exists():
        return [Category(name) for name in _DEFAULT_NAMES]
    return _parse_document(_read_document(path))


def add_category(vault: Path, name: str) -> str:
    """Append a checked category or keep the existing name and selection."""
    name = validate_category(name)
    path = _category_path(vault)
    text = _read_document(path) if path.exists() else _DEFAULT_DOCUMENT
    categories = _parse_document(text)
    for category in categories:
        if category.name.casefold() == name.casefold():
            return category.name
    path = ensure_categories(vault)
    path = _category_path(vault)
    newline = "\r\n" if "\r\n" in text else "\n"
    separator = "" if not text or text.endswith(("\n", "\r")) else newline
    try:
        with path.open("a", encoding="utf-8", newline="") as document:
            document.write(f"{separator}- [x] {name}{newline}")
    except OSError:
        raise CategoryError("새 분류를 저장하지 못했습니다. 보관함 경로와 권한을 확인하세요.") from None
    return name


def render_categories(config_text: str, categories: list[Category]) -> str:
    """Replace only the sidebar block delimited by the two exact markers."""
    lines = config_text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip("\r\n").rstrip(" \t") == _START]
    ends = [index for index, line in enumerate(lines) if line.rstrip("\r\n").rstrip(" \t") == _END]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise CategoryError("_quarto.yml에서 BLOG-CATEGORIES-START/END 분류 영역을 확인하세요.")
    names: list[str] = []
    seen: set[str] = set()
    for category in categories:
        if not isinstance(category, Category) or not isinstance(category.selected, bool):
            raise CategoryError("분류 이름과 체크 상태를 확인하세요.")
        name = validate_category(category.name)
        if name.casefold() in seen:
            raise CategoryError("같은 이름의 분류가 중복되어 있습니다.")
        seen.add(name.casefold())
        if category.selected:
            names.append(name)
    newline = "\r\n" if lines[starts[0]].endswith("\r\n") else "\n"
    block: list[str] = []
    if names:
        block.extend(['      - section: "논문 리뷰"', "        contents:"])
        for name in names:
            block.extend([
                f"          - text: {json.dumps(name, ensure_ascii=False)}",
                f"            href: {json.dumps('reviews.qmd#category=' + quote(name, safe=''), ensure_ascii=False)}",
            ])
    replacement = "".join(line + newline for line in block)
    return "".join(lines[:starts[0] + 1]) + replacement + "".join(lines[ends[0]:])
