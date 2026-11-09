"""Read selected references and private notes through Zotero's local API."""

from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class ZoteroError(Exception):
    """A safe, user-facing connection or reference error."""


def citation_key(item_key: str) -> str:
    if not isinstance(item_key, str) or not re.fullmatch(r"[A-Z0-9]{8}", item_key):
        raise ZoteroError("Zotero 항목 키는 대문자·숫자 8자리여야 합니다.")
    return f"zotero-{item_key}"


def _text(value: object) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value) if isinstance(value, str) else ""


def _escape(value: str) -> str:
    value = value.replace("\\", "\\\\").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\[\]`*_#|])", r"\\\1", value)


def _url(value: object, *, note: bool = False) -> str | None:
    if not isinstance(value, str) or re.search(r"[\x00-\x20\x7f]", value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.username or parsed.password or not parsed.hostname:
            return None
        if parsed.scheme in ({"https"} if note else {"http", "https"}):
            return value.replace("(", "%28").replace(")", "%29")
        if note and parsed.scheme == "zotero" and parsed.netloc in {"select", "open-pdf"}:
            if re.fullmatch(r"/library/items/[A-Z0-9]{8}", parsed.path):
                return value.replace("(", "%28").replace(")", "%29")
    except ValueError:
        pass
    return None


class _NoteParser(HTMLParser):
    """Convert a small HTML subset without importing remote media or raw HTML."""

    BLOCKS = {"p", "div", "section", "article", "blockquote", "ul", "ol", "h1", "h2", "h3", "h4"}
    HIDDEN = {"script", "style", "iframe", "object", "embed", "svg", "template", "noscript"}

    def __init__(self, *, markdown: bool = True):
        super().__init__(convert_charrefs=True)
        self.markdown = markdown
        self.parts: list[str] = []
        self.hidden: list[str] = []
        self.links: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HIDDEN:
            if tag not in {"embed"}:
                self.hidden.append(tag)
            return
        if self.hidden:
            return
        if tag in self.BLOCKS or tag == "li":
            self.parts.append("\n\n")
            if tag == "li" and self.markdown:
                self.parts.append("- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"strong", "b", "em", "i"} and self.markdown:
            self.parts.append("**" if tag in {"strong", "b"} else "*")
        elif tag == "a" and self.markdown:
            target = _url(dict(attrs).get("href"), note=True)
            self.links.append(target)
            if target:
                self.parts.append("[")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in {"br", "img", "hr", "embed", "input"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag in self.BLOCKS or tag == "li":
            self.parts.append("\n\n")
        elif tag in {"strong", "b", "em", "i"} and self.markdown:
            self.parts.append("**" if tag in {"strong", "b"} else "*")
        elif tag == "a" and self.markdown and self.links:
            target = self.links.pop()
            if target:
                self.parts.append(f"]({target})")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(_escape(_text(data)) if self.markdown else _text(data))

    def render(self, value: str) -> str:
        self.feed(_text(value))
        self.close()
        return re.sub(r"\n{3,}", "\n\n", "".join(self.parts)).strip()


def _plain(value: object) -> str:
    return re.sub(r"\s+", " ", _NoteParser(markdown=False).render(_text(value))).strip()


CSL_FIELDS = {
    "id", "type", "title", "author", "editor", "issued", "container-title", "volume",
    "issue", "page", "publisher", "publisher-place", "edition", "DOI", "ISBN", "ISSN",
    "URL", "event-title", "number", "language", "accessed",
}
NAME_FIELDS = {"family", "given", "literal", "suffix", "dropping-particle", "non-dropping-particle"}
LOCAL_PATH = re.compile(r"(?:file:|(?:^|\s)(?:~[/\\]|/(?:Users|home|private|tmp|var)/|[A-Za-z]:[/\\]))", re.I)


def csl_author_names(reference: dict) -> list[str]:
    names = [name.get("literal") or " ".join(filter(None, (name.get("given"), name.get("family"))))
             for name in reference.get("author", [])]
    return list(filter(None, names))


def _csl_text(value: object) -> str | None:
    cleaned = _plain(value)
    return cleaned if cleaned and not LOCAL_PATH.search(cleaned) else None


def _sanitize_csl(source: dict, key: str) -> dict:
    result: dict = {"id": citation_key(key)}
    for field in CSL_FIELDS - {"id"}:
        value = source.get(field)
        if field == "URL":
            if (target := _url(value)) and not LOCAL_PATH.search(target):
                result[field] = target
        elif field in {"author", "editor"} and isinstance(value, list):
            names = []
            for name in value:
                if isinstance(name, dict):
                    safe = {k: cleaned for k in NAME_FIELDS if (cleaned := _csl_text(name.get(k)))}
                    if safe:
                        names.append(safe)
            if names:
                result[field] = names
        elif field in {"issued", "accessed"} and isinstance(value, dict):
            date: dict = {}
            parts = value.get("date-parts")
            if isinstance(parts, list):
                safe_parts = [p[:3] for p in parts if isinstance(p, list) and p and
                              all(isinstance(n, int) and not isinstance(n, bool) for n in p[:3])]
                if safe_parts:
                    date["date-parts"] = safe_parts[:2]
            for name in ("raw", "literal"):
                if cleaned := _csl_text(value.get(name)):
                    date[name] = cleaned
            if isinstance(value.get("circa"), bool):
                date["circa"] = value["circa"]
            if date:
                result[field] = date
        elif isinstance(value, str):
            if cleaned := _csl_text(value):
                result[field] = cleaned
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if str(value) not in {"nan", "inf", "-inf"}:
                result[field] = value
    return result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ZoteroClient:
    def __init__(self, base_url: str = "http://127.0.0.1:23119", timeout: float = 10):
        try:
            parsed = urlsplit(base_url)
            valid = (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
                     and parsed.port == 23119 and not parsed.username and not parsed.password
                     and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ZoteroError("Zotero 연결 주소는 이 컴퓨터의 localhost 또는 127.0.0.1:23119여야 합니다.")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 120:
            raise ZoteroError("Zotero 연결 대기 시간은 0초 초과, 120초 이하여야 합니다.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _request_json(self, path: str, **params) -> object:
        url = f"{self.base_url}/api/users/0/{path}"
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={"Zotero-API-Version": "3", "Accept": "application/json"}, method="GET")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                body = response.read(16 * 1024 * 1024 + 1)
            if len(body) > 16 * 1024 * 1024:
                raise ZoteroError("Zotero 응답이 너무 큽니다. 가져올 항목을 줄여 주세요.")
            return json.loads(body.decode("utf-8"))
        except HTTPError as error:
            status = error.code
            error.close()
            if status == 403:
                raise ZoteroError("Zotero 설정 → 고급에서 ‘다른 응용 프로그램이 Zotero와 통신하도록 허용’을 켜 주세요.") from None
            if status == 404:
                raise ZoteroError("Zotero에서 선택한 항목을 찾지 못했습니다. 항목 키를 확인해 주세요.") from None
            raise ZoteroError(f"Zotero가 요청을 처리하지 못했습니다. 응답 코드: {status}.") from None
        except (URLError, OSError, TimeoutError):
            raise ZoteroError("Zotero에 연결하지 못했습니다. Zotero를 열고 연결 설정을 확인해 주세요.") from None
        except (UnicodeError, json.JSONDecodeError):
            raise ZoteroError("Zotero 응답을 읽지 못했습니다. 연결 상태와 항목을 확인해 주세요.") from None

    @staticmethod
    def _data(item: dict) -> dict:
        data = item.get("data", item)
        return data if isinstance(data, dict) else {}

    def list_items(self, limit: int = 30) -> list[dict]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ZoteroError("가져올 목록 수는 1 이상의 정수여야 합니다.")
        raw = self._request_json("items/top", limit=limit, sort="dateAdded", direction="desc", format="json")
        if not isinstance(raw, list):
            raise ZoteroError("Zotero 항목 목록의 형식을 확인하지 못했습니다.")
        items = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            data = self._data(item)
            kind, key = data.get("itemType"), item.get("key", data.get("key"))
            if kind in {None, "note", "attachment", "annotation"} or not isinstance(key, str) or not re.fullmatch(r"[A-Z0-9]{8}", key):
                continue
            items.append({"key": key, "title": _plain(data.get("title")), "itemType": kind})
        return items

    def get_item(self, key: str) -> dict:
        citation_key(key)
        value = self._request_json(f"items/{key}", format="json")
        if not isinstance(value, dict):
            raise ZoteroError("Zotero 항목 정보의 형식을 확인하지 못했습니다.")
        return value

    def get_children(self, key: str) -> list:
        citation_key(key)
        value = self._request_json(f"items/{key}/children", format="json")
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ZoteroError("Zotero 메모와 첨부 항목의 형식을 확인하지 못했습니다.")
        return value

    def get_csl(self, key: str) -> dict:
        citation_key(key)
        value = self._request_json(f"items/{key}", format="csljson")
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, dict) or not isinstance(value.get("type"), str) or not value.get("type"):
            raise ZoteroError("Zotero에서 참고문헌 정보를 가져오지 못했습니다. 논문 항목을 선택해 주세요.")
        return _sanitize_csl(value, key)

    def export_references(self, keys: list[str]) -> list[dict]:
        selected = []
        for key in keys:
            citation_key(key)
            if key not in selected:
                selected.append(key)
        return [self.get_csl(key) for key in selected]

    @staticmethod
    def _annotation_page(data: dict) -> int | None:
        position = data.get("annotationPosition")
        if isinstance(position, str):
            try:
                position = json.loads(position)
            except (ValueError, TypeError):
                position = None
        if isinstance(position, dict):
            index = position.get("pageIndex")
            if isinstance(index, int) and not isinstance(index, bool) and index >= 0:
                return index + 1
        label = str(data.get("annotationPageLabel", ""))
        return int(label) if re.fullmatch(r"[0-9]+", label) and int(label) > 0 else None

    def literature_markdown(self, key: str) -> str:
        item = self.get_item(key)
        data = self._data(item)
        if data.get("itemType") in {None, "note", "attachment", "annotation"}:
            raise ZoteroError("메모나 첨부 파일 대신 논문 항목을 선택해 주세요.")
        csl = self.get_csl(key)
        title = _plain(csl.get("title") or data.get("title")) or "제목 없음"
        zotero_link = f"zotero://select/library/items/{key}"
        metadata = {"title": title, "zotero_key": key, "citation_key": citation_key(key), "zotero_link": zotero_link}
        lines = ["---", *[f"{name}: {json.dumps(value, ensure_ascii=False)}" for name, value in metadata.items()], "---", "", f"# {_escape(title)}", "", "## 서지정보", ""]
        authors = csl_author_names(csl)
        date = csl.get("issued", {})
        year = str(date["date-parts"][0][0]) if date.get("date-parts") else date.get("raw", "연도 미확인")
        summary = ". ".join(filter(None, [", ".join(authors), f"({year})", title, str(csl.get("container-title", ""))])) + "."
        lines.extend([_escape(summary), "", f"[Zotero에서 열기]({zotero_link})", ""])
        public_url = csl.get("URL")
        if not public_url and csl.get("DOI"):
            doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(csl["DOI"]), flags=re.I)
            public_url = "https://doi.org/" + quote(doi, safe="/:")
        if public_url:
            lines.extend([f"[논문 링크]({public_url})", ""])
        children = self.get_children(key)
        notes = [self._data(child) for child in children if self._data(child).get("itemType") == "note"]
        if notes:
            lines.extend(["## Zotero 메모", ""])
            for number, note in enumerate(notes, 1):
                content = _NoteParser().render(_text(note.get("note")))
                if content:
                    lines.extend([f"### 메모 {number}", "", content, ""])
        annotation_lines: list[str] = []
        seen: set[str] = set()
        for child in children:
            attachment = self._data(child)
            if attachment.get("itemType") != "attachment" or not (attachment.get("contentType") == "application/pdf" or _text(attachment.get("filename")).lower().endswith(".pdf")):
                continue
            pdf_key = child.get("key", attachment.get("key"))
            citation_key(pdf_key)
            for annotation in self.get_children(pdf_key):
                annot = self._data(annotation)
                if annot.get("itemType") != "annotation":
                    continue
                annotation_key = annotation.get("key", annot.get("key"))
                citation_key(annotation_key)
                if annotation_key in seen:
                    continue
                seen.add(annotation_key)
                text = _NoteParser().render(_text(annot.get("annotationText")))
                comment = _NoteParser().render(_text(annot.get("annotationComment")))
                if not text and not comment:
                    continue
                page = self._annotation_page(annot)
                params = {"annotation": annotation_key}
                if page:
                    params = {"page": page, **params}
                link = f"zotero://open-pdf/library/items/{pdf_key}?{urlencode(params)}"
                label = _plain(annot.get("annotationPageLabel")) or (str(page) if page else "위치 확인")
                annotation_lines.extend([f"### [페이지 {_escape(label)}]({link})", ""])
                if text:
                    annotation_lines.extend(["\n".join("> " + line for line in text.splitlines()), ""])
                if comment:
                    annotation_lines.extend(["메모: " + comment, ""])
        if annotation_lines:
            lines.extend(["## PDF 주석", "", *annotation_lines])
        lines.extend(["## 내 생각", ""])
        return "\n".join(lines).rstrip() + "\n"
