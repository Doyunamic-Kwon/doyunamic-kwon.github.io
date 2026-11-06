"""Export explicitly approved Obsidian reviews into a Quarto website."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlsplit
import xml.etree.ElementTree as ET

from zotero_client import ZoteroClient, ZoteroError
from obsidian_tree import FolderError, TreeEntry, render_tree


class PublishError(Exception):
    """A review needs attention before it can be exported."""


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def yaml_header(fields: dict) -> str:
    return "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fields.items()) + "\n---\n\n"


def safe_inside(path: Path, root: Path) -> Path:
    resolved, boundary = path.resolve(), root.resolve()
    if not resolved.is_relative_to(boundary):
        raise PublishError("선택한 파일 또는 그림이 Obsidian Vault 밖을 가리킵니다.")
    return resolved


def strip_private_comments(source: str) -> str:
    """Remove Obsidian %% comments outside code; leave fenced examples intact."""
    parts = source.split("\n")
    output: list[str] = []
    fence_char, fence_size = "", 0
    comment = False
    in_frontmatter = bool(parts and parts[0].strip() == "---")
    for number, line in enumerate(parts):
        if in_frontmatter:
            output.append(line)
            if number > 0 and line.strip() in {"---", "..."}:
                in_frontmatter = False
            continue
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if not comment and match:
            marker = match[1]
            if not fence_char:
                fence_char, fence_size = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_size:
                fence_char, fence_size = "", 0
            output.append(line)
            continue
        if fence_char:
            output.append(line)
            continue
        rendered, cursor, inline_ticks = [], 0, 0
        while cursor < len(line):
            if line[cursor] == "`" and not comment:
                end = cursor
                while end < len(line) and line[end] == "`":
                    end += 1
                count = end - cursor
                if not inline_ticks:
                    inline_ticks = count
                elif count == inline_ticks:
                    inline_ticks = 0
                rendered.append(line[cursor:end])
                cursor = end
                continue
            if line[cursor:cursor + 2] == "%%" and not inline_ticks:
                comment = not comment
                cursor += 2
                continue
            if not comment:
                rendered.append(line[cursor])
            cursor += 1
        output.append("".join(rendered))
    if comment:
        raise PublishError("닫히지 않은 Obsidian %% 주석이 있습니다.")
    return "\n".join(output)


def inline_text(value: object) -> str:
    if isinstance(value, list):
        return "".join(inline_text(x) for x in value)
    if not isinstance(value, dict):
        return str(value) if isinstance(value, (str, int, float)) else ""
    kind, content = value.get("t"), value.get("c")
    if kind == "Str":
        return content
    if kind in {"Space", "SoftBreak", "LineBreak"}:
        return " "
    if kind in {"Code", "Math"}:
        return content[-1]
    return inline_text(content)


def meta_value(value: dict) -> object:
    kind, content = value.get("t"), value.get("c")
    if kind in {"MetaBool", "MetaString"}:
        return content
    if kind == "MetaList":
        return [meta_value(v) for v in content]
    if kind == "MetaMap":
        return {k: meta_value(v) for k, v in content.items()}
    return inline_text(content).strip()


class Pandoc:
    def __init__(self, quarto: str):
        self.quarto = quarto

    def _convert(self, text: str, input_format: str, output_format: str) -> str:
        result = subprocess.run(
            [self.quarto, "pandoc", f"--from={input_format}", f"--to={output_format}", "--wrap=none"],
            input=text, text=True, capture_output=True,
        )
        if result.returncode:
            raise PublishError("리뷰의 Markdown 또는 제목·날짜 설정을 읽지 못했습니다.")
        return result.stdout

    def parse(self, source: str) -> dict:
        return json.loads(self._convert(strip_private_comments(source), "markdown+wikilinks_title_after_pipe", "json"))

    def markdown(self, document: dict) -> str:
        clean = {**document, "meta": {}}
        return self._convert(json.dumps(clean, ensure_ascii=False), "json", "markdown").strip() + "\n"


@dataclass
class Review:
    path: Path
    meta: dict
    document: dict
    slug: str
    source_id: str


class ObsidianPublisher:
    MARKER = "_obsidian-import.json"
    IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg"}
    PUBLIC_FIELDS = {"title", "description", "categories", "date", "date-modified", "subtitle", "lang"}

    def __init__(self, root: Path, config: dict, pandoc: Pandoc, client: ZoteroClient | None = None):
        self.root = root.resolve()
        self.vault = Path(config["vault"]).expanduser().resolve()
        if not self.vault.is_dir():
            raise PublishError("설정한 Obsidian Vault를 찾지 못했습니다.")
        self.reviews = safe_inside(self.vault / config.get("reviews", "Blog/Reviews"), self.vault)
        self.pandoc = pandoc
        self.client = client or ZoteroClient()
        identity = self.vault / "Blog/.blog-vault-id"
        if not identity.is_file():
            raise PublishError("먼저 ‘연결 설정’ 작업으로 Obsidian 작성 폴더를 준비하세요.")
        self.vault_id = identity.read_text().strip()
        if not re.fullmatch(r"[a-f0-9]{32}", self.vault_id):
            raise PublishError("Obsidian 작성 폴더의 연결 정보를 확인하세요.")
        self._documents: dict[Path, tuple[dict, dict]] = {}
        self._file_index: dict[str, list[Path]] | None = None

    def read(self, path: Path) -> tuple[dict, dict]:
        path = safe_inside(path, self.vault)
        if path not in self._documents:
            if not path.is_file() or path.suffix.lower() != ".md":
                raise PublishError("Obsidian의 Markdown 리뷰 파일을 선택하세요.")
            if path.stat().st_size > 2 * 1024 * 1024:
                raise PublishError("리뷰 파일이 너무 큽니다. 긴 첨부 자료는 별도 파일로 정리하세요.")
            document = self.pandoc.parse(path.read_text(encoding="utf-8-sig"))
            meta = {k: meta_value(v) for k, v in document.get("meta", {}).items()}
            self._documents[path] = meta, document
        return self._documents[path]

    def review(self, path: Path, *, allow_draft: bool = False) -> Review:
        path = safe_inside(path, self.reviews)
        meta, document = self.read(path)
        if not allow_draft and meta.get("blog_publish") is not True:
            raise PublishError("블로그 공개를 선택한 글만 가져옵니다. 해당 글의 blog_publish를 true로 설정하세요.")
        slug = meta.get("blog_slug")
        if not isinstance(slug, str) or len(slug) > 80 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise PublishError("리뷰의 blog_slug에 소문자·숫자·하이픈으로 된 글 주소를 적으세요.")
        title = meta.get("title")
        if not isinstance(title, str) or not title.strip() or ("[논문 제목]" in title and not allow_draft):
            raise PublishError("리뷰의 실제 제목을 작성하세요.")
        relative = path.relative_to(self.reviews).as_posix()
        source_id = hashlib.sha256(relative.encode()).hexdigest()
        return Review(path, meta, document, slug, source_id)

    def candidates(self, *, ready_only: bool = True) -> list[Review]:
        result, slugs = [], set()
        for path in sorted(self.reviews.rglob("*.md")):
            if any(part.startswith('.') for part in path.relative_to(self.reviews).parts):
                continue
            meta, _ = self.read(path)
            if ready_only and meta.get("blog_publish") is not True:
                continue
            if not ready_only and not meta.get('blog_slug') and meta.get('blog_publish') is not True:
                continue
            review = self.review(path, allow_draft=not ready_only)
            if review.slug in slugs:
                raise PublishError("같은 blog_slug를 사용하는 리뷰가 두 개 있습니다.")
            slugs.add(review.slug)
            result.append(review)
        return result

    def _index(self) -> dict[str, list[Path]]:
        if self._file_index is None:
            self._file_index = {}
            for parent, directories, files in os.walk(self.vault):
                directories[:] = [d for d in directories if not d.startswith(".")]
                for name in files:
                    self._file_index.setdefault(name, []).append(Path(parent) / name)
        return self._file_index

    def resolve_link(self, target: str, source: Path, *, note: bool) -> Path:
        target = unquote(target)
        if "\\" in target or target.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", target):
            raise PublishError("글과 그림의 링크에는 Vault 안의 상대 경로를 사용하세요.")
        names = [target]
        if note and not Path(target).suffix:
            names.append(target + ".md")
        candidates = []
        for name in names:
            for path in (source.parent / name, self.vault / name):
                resolved = path.resolve()
                if not resolved.is_relative_to(self.vault):
                    continue
                if resolved.is_file() and resolved not in candidates:
                    candidates.append(resolved)
        if not candidates and "/" not in target:
            for name in names:
                for path in self._index().get(name, []):
                    resolved = safe_inside(path, self.vault)
                    if resolved not in candidates:
                        candidates.append(resolved)
        if len(candidates) != 1:
            raise PublishError("링크한 글이나 그림을 하나로 찾지 못했습니다. Vault 안의 정확한 상대 경로를 적으세요.")
        return candidates[0]

    @staticmethod
    def _safe_svg(content: bytes) -> None:
        try:
            tree = ET.fromstring(content)
        except ET.ParseError:
            raise PublishError("SVG 그림을 읽지 못했습니다.") from None
        for element in tree.iter():
            if element.tag.split("}")[-1].lower() in {"script", "foreignobject", "iframe"}:
                raise PublishError("이 SVG는 웹 실행 요소를 포함합니다. PNG 등으로 내보내세요.")
            for key, value in element.attrib.items():
                name = key.split("}")[-1].lower()
                if name.startswith("on") or (name == "href" and not value.startswith("#")):
                    raise PublishError("이 SVG는 다른 파일 또는 실행 요소를 참조합니다. PNG 등으로 내보내세요.")
        if re.search(rb"url\(\s*['\"]?(?!#)", content, re.I):
            raise PublishError("이 SVG는 다른 파일을 참조합니다. PNG 등으로 내보내세요.")

    def export(self, review: Review, destination: Path, public_reviews: list[Review], *, preview: bool = False) -> dict:
        destination.mkdir(parents=True, exist_ok=False)
        public_by_path = {r.path: r for r in public_reviews}
        if review.meta.get("blog_publish") is not True:
            public_by_path[review.path] = review
        document = json.loads(json.dumps(review.document))
        citations: set[str] = set()
        asset_paths: dict[Path, str] = {}
        dropped = object()

        def heading_id(linked: Review, fragment: str) -> str:
            requested = unquote(fragment)
            found = []
            def visit(value):
                if isinstance(value, list):
                    for child in value:
                        visit(child)
                elif isinstance(value, dict):
                    if value.get("t") == "Header":
                        _, attributes, text = value["c"]
                        if requested in {attributes[0], inline_text(text)}:
                            found.append(attributes[0])
                    visit(value.get("c"))
            visit(linked.document["blocks"])
            if len(set(found)) != 1:
                raise PublishError("링크한 글에서 제목 위치를 찾지 못했습니다. 해당 제목 또는 링크를 확인하세요.")
            return quote(found[0], safe="-_")

        def transform(node):
            if isinstance(node, list):
                return [value for child in node if (value := transform(child)) is not dropped]
            if not isinstance(node, dict):
                return node
            kind, content = node.get("t"), node.get("c")
            if kind in {"RawBlock", "RawInline"}:
                fmt, text = content
                if fmt == "html" and re.fullmatch(r"\s*(?:<!--.*?-->\s*)+", text, re.S):
                    return dropped
                if fmt == "html" and re.fullmatch(r"\s*</?(?:br|sup|sub|kbd|mark)\s*/?>\s*", text, re.I):
                    return node
                raise PublishError("공개 리뷰의 HTML은 Markdown 문법으로 바꾸세요. 주석은 자동으로 제외합니다.")
            if kind == "Cite":
                for citation in content[0]:
                    citations.add(citation["citationId"])
            if kind in {"Image", "Link"}:
                attributes, label, pair = content
                target, title = pair
                parsed = urlsplit(target)
                wiki_link = "wikilink" in attributes[1]
                attributes[1] = [x for x in attributes[1] if x != "wikilink"]
                if not target:
                    raise PublishError("빈 글 또는 그림 링크가 있습니다.")
                if parsed.scheme or parsed.netloc:
                    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
                        raise PublishError("공개 글의 링크에는 https 웹 주소 또는 공개할 글의 상대 경로를 사용하세요.")
                    if kind == "Image" and parsed.scheme != "https":
                        raise PublishError("외부 그림에는 https 주소를 사용하세요.")
                elif kind == "Link" and target.startswith("#"):
                    if wiki_link:
                        pair[0] = "#" + heading_id(review, parsed.fragment)
                elif kind == "Image":
                    if parsed.query or parsed.fragment:
                        raise PublishError("로컬 그림 링크에는 파일 경로만 적으세요.")
                    path = self.resolve_link(parsed.path, review.path, note=False)
                    extension = path.suffix.lower()
                    if extension not in self.IMAGE_TYPES:
                        raise PublishError("글 포함이나 PDF 첨부 대신 PNG·JPG·SVG 등의 그림 파일을 연결하세요.")
                    if path not in asset_paths:
                        if path.stat().st_size > 32 * 1024 * 1024:
                            raise PublishError("그림 한 개의 크기는 32MB 이하여야 합니다.")
                        data = path.read_bytes()
                        if extension == ".svg":
                            self._safe_svg(data)
                        relative = f"assets/{hashlib.sha256(data).hexdigest()[:20]}{extension}"
                        (destination / "assets").mkdir(exist_ok=True)
                        (destination / relative).write_bytes(data)
                        asset_paths[path] = relative
                    pair[0] = asset_paths[path]
                else:
                    path = self.resolve_link(parsed.path, review.path, note=True)
                    linked = public_by_path.get(path)
                    if not linked:
                        raise PublishError("개인 메모로 이어지는 링크가 있습니다. 함께 공개할 리뷰를 지정하거나 해당 링크를 본문에서 제외하세요.")
                    pair[0] = f"/posts/{linked.slug}/" + (f"#{heading_id(linked, parsed.fragment)}" if parsed.fragment else "")
            if "c" in node:
                node["c"] = transform(content)
            else:
                for key, value in node.items():
                    if isinstance(value, (dict, list)):
                        node[key] = transform(value)
            return node

        document["blocks"] = transform(document["blocks"])
        markdown = self.pandoc.markdown(document)
        if not preview and re.search(r"\[(?:논문 제목|핵심 질문|값|Dataset · split)\]", markdown):
            raise PublishError("리뷰 본문에 템플릿의 빈 항목이 남아 있습니다.")
        if re.search(r"(?:file://|obsidian://|/(?:Users|home|private)/|[A-Za-z]:\\)", markdown, re.I):
            raise PublishError("공개 글에 개인 파일 경로가 남아 있습니다.")
        keys = []
        for citation in sorted(citations):
            if re.match(r"^(?:fig|tbl|eq|sec|lst)-", citation):
                continue
            if not re.fullmatch(r"zotero-[A-Z0-9]{8}", citation):
                raise PublishError("이 흐름에서는 Zotero에서 가져온 zotero-항목키 형식의 인용을 사용하세요.")
            keys.append(citation.removeprefix("zotero-"))
        try:
            references = self.client.export_references(keys) if keys else []
        except ZoteroError as error:
            raise PublishError(str(error)) from None
        meta = {k: v for k, v in review.meta.items() if k in self.PUBLIC_FIELDS}
        for field in ("date", "date-modified"):
            if field in meta:
                try:
                    date.fromisoformat(str(meta[field]))
                except ValueError:
                    raise PublishError(f"{field}에는 YYYY-MM-DD 형식의 날짜를 적으세요.") from None
        if not isinstance(meta.get("categories", []), list) or not all(isinstance(x, str) for x in meta.get("categories", [])):
            raise PublishError("categories에는 [LLM, RAG]와 같은 주제 목록을 적으세요.")
        if re.search(r"(?:file://|/(?:Users|home|private)/)", json.dumps(meta, ensure_ascii=False), re.I):
            raise PublishError("리뷰 제목이나 설명에 개인 파일 경로가 남아 있습니다.")
        meta.update({"draft": False, "toc": True})
        if references:
            meta["bibliography"] = "references.json"
            write_json(destination / "references.json", references)
        (destination / "index.md").write_text(yaml_header(meta) + markdown, encoding="utf-8")
        files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in destination.rglob("*") if p.is_file()}
        relative = review.path.relative_to(self.reviews)
        marker = {"version": 1, "vault_id": self.vault_id, "source_id": review.source_id, "files": files,
                  "navigation": {"folders": list(relative.parent.parts), "label": relative.stem}}
        write_json(destination / self.MARKER, marker)
        return marker

    def managed(self) -> dict[str, tuple[Path, dict]]:
        managed = {}
        posts = self.root / "posts"
        for path in posts.glob(f"*/{self.MARKER}"):
            safe_inside(path, posts)
            if path.is_symlink() or path.parent.is_symlink():
                raise PublishError("게시 폴더의 연결 파일을 일반 파일로 바꿔 주세요.")
            try:
                marker = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                raise PublishError("블로그로 가져온 글의 관리 정보를 읽지 못했습니다.") from None
            if marker.get("vault_id") == self.vault_id:
                managed[path.parent.name] = path.parent, marker
        return managed

    def verify_managed(self, path: Path, marker: dict) -> None:
        safe_inside(path, self.root / "posts")
        expected = set(marker.get("files", {})) | {self.MARKER}
        actual = {p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()}
        if actual != expected:
            raise PublishError("블로그 복사본에 별도로 추가한 파일이 있습니다. Obsidian 원본과 먼저 맞춰 주세요.")
        for relative, checksum in marker.get("files", {}).items():
            file = safe_inside(path / relative, path)
            if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != checksum:
                raise PublishError("블로그 복사본이 직접 수정됐습니다. 변경 내용을 Obsidian 원본에 먼저 반영하세요.")

    def sync(self) -> dict[str, list[str]]:
        ready = self.candidates()
        work = self.root / "work"
        work.mkdir(exist_ok=True)
        current = self.managed()
        for path, marker in current.values():
            self.verify_managed(path, marker)
        plan = {"updated": [], "removed": []}
        with tempfile.TemporaryDirectory(prefix="obsidian-export-", dir=work) as temporary:
            staging = Path(temporary)
            for review in ready:
                existing = self.root / "posts" / review.slug
                if existing.exists() and review.slug not in current:
                    raise PublishError("같은 주소의 기존 블로그 글이 있습니다. blog_slug를 바꿔 주세요.")
                self.export(review, staging / review.slug, ready)
            keep = {r.slug for r in ready}
            for slug, (path, _) in current.items():
                if slug not in keep:
                    shutil.rmtree(path)
                    plan["removed"].append(slug)
            for review in ready:
                target = self.root / "posts" / review.slug
                if target.exists():
                    shutil.rmtree(target)
                shutil.move(str(staging / review.slug), str(target))
                plan["updated"].append(review.slug)
        return plan

    def website_project(self, folder: Path, source_paths: list[str]) -> Path:
        folder.mkdir(parents=True, exist_ok=False)
        for relative in source_paths:
            parts = Path(relative).parts
            if not parts or parts[0] in {"docs", "scripts", "tests", "templates", "work", "outputs"}:
                continue
            if relative.endswith(".command") or Path(relative).name in {self.MARKER, ".gitignore", "README.md"}:
                continue
            path = safe_inside(self.root / relative, self.root)
            if path.is_file():
                target = safe_inside(folder / relative, folder)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        self.write_navigation(folder)
        return folder

    def write_navigation(self, project: Path) -> None:
        entries = []
        for post in sorted((project / "posts").glob("*")):
            if not post.is_dir() or not any((post / name).is_file() for name in ("index.md", "index.qmd")):
                continue
            marker = post / self.MARKER
            if not marker.is_file():
                marker = self.root / "posts" / post.name / self.MARKER
            navigation = {}
            if marker.is_file():
                try:
                    navigation = json.loads(marker.read_text()).get("navigation", {})
                except (OSError, ValueError, AttributeError):
                    raise PublishError("게시한 글의 폴더 정보를 읽지 못했습니다. Obsidian에서 다시 가져오세요.") from None
            if not isinstance(navigation, dict):
                raise PublishError("게시한 글의 폴더 정보를 확인하세요.")
            folders = navigation.get("folders", [])
            label = navigation.get("label", post.name)
            if not isinstance(folders, list) or not all(isinstance(part, str) for part in folders) or not isinstance(label, str):
                raise PublishError("게시한 글의 폴더 정보를 확인하세요.")
            entries.append(TreeEntry(tuple(folders), label, f"/posts/{post.name}/"))
        settings = project / "_quarto.yml"
        if settings.is_file():
            try:
                settings.write_text(render_tree(settings.read_text(), entries))
            except FolderError as error:
                raise PublishError(str(error)) from None

    def preview_project(self, review: Review, source_paths: list[str]) -> Path:
        work = self.root / "work"
        work.mkdir(exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="review-preview-", dir=work)) / "project"
        self.website_project(folder, source_paths)
        for slug in self.managed():
            copied = folder / "posts" / slug
            if copied.exists():
                shutil.rmtree(copied)
        ready = [r for r in self.candidates() if r.path != review.path] + [review]
        for candidate in ready:
            target = folder / "posts" / candidate.slug
            if target.exists():
                raise PublishError("같은 주소의 기존 블로그 글이 있습니다. blog_slug를 바꿔 주세요.")
            self.export(candidate, target, ready, preview=True)
        self.write_navigation(folder)
        return folder
