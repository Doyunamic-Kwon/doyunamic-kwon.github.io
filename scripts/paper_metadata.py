"""Extract publication metadata without inferring acceptance or publication status."""

from __future__ import annotations

import datetime as dt
from calendar import month_abbr
import re
import unicodedata
from urllib.parse import quote, unquote, urlsplit

from zotero_client import _plain, _url, csl_author_names


_LOCAL_PATH = re.compile(
    r"(?:file:|(?:^|\s)(?:~[/\\]|[A-Za-z]:[/\\]|\\\\|"
    r"/(?:Users|home|private|tmp|var|Volumes|Applications|Library|etc|mnt|media)/))",
    re.IGNORECASE,
)


def _clean(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = "".join(" " if ch in "\t\r\n" else ch for ch in value
                    if ch in "\t\r\n" or unicodedata.category(ch) not in {"Cc", "Cf"})
    for _ in range(3):
        cleaned = _plain(value)
        if cleaned == value:
            break
        value = cleaned
    if value.startswith(("/", "\\", "~/", "~\\")) or _LOCAL_PATH.search(value):
        return ""
    return value.strip()


def _parts_date(parts: object) -> str:
    if not isinstance(parts, (list, tuple)) or not 1 <= len(parts) <= 3:
        return ""
    if not all(isinstance(part, int) and not isinstance(part, bool) for part in parts):
        return ""
    try:
        dt.date(parts[0], parts[1] if len(parts) >= 2 else 1, parts[2] if len(parts) == 3 else 1)
    except ValueError:
        return ""
    return "-".join(f"{part:04d}" if index == 0 else f"{part:02d}" for index, part in enumerate(parts))


def _date_text(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return _parts_date([value])
    value = _clean(value)
    match = re.fullmatch(r"([0-9]{4})(?:[-/.]([0-9]{1,2})(?:[-/.]([0-9]{1,2}))?)?", value)
    if match:
        return _parts_date([int(part) for part in match.groups() if part is not None])
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ].+", value):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return ""
    korean = re.fullmatch(r"([0-9]{4})\s*년(?:\s*([0-9]{1,2})\s*월(?:\s*([0-9]{1,2})\s*일)?)?", value)
    if korean:
        return _parts_date([int(part) for part in korean.groups() if part is not None])
    for date_format in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%B %Y", "%b %Y"):
        try:
            parsed = dt.datetime.strptime(value, date_format)
            return parsed.date().isoformat() if "%d" in date_format else parsed.strftime("%Y-%m")
        except ValueError:
            continue
    return ""


def _issued_date(issued: object) -> str:
    if not isinstance(issued, dict):
        return ""
    parts = issued.get("date-parts")
    if isinstance(parts, list) and 1 <= len(parts) <= 2:
        dates = [_parts_date(part) for part in parts]
        if all(dates):
            return " – ".join(dates)
    return _date_text(issued.get("raw")) or _date_text(issued.get("literal"))


def _doi(value: object) -> str:
    if not isinstance(value, str):
        return ""
    candidate = _clean(value.strip().strip("<>"))
    candidate = re.sub(r"^doi\s*:\s*", "", candidate, flags=re.IGNORECASE)
    if re.match(r"^https?://", candidate, flags=re.IGNORECASE):
        try:
            parsed = urlsplit(candidate)
            if parsed.hostname not in {"doi.org", "dx.doi.org"} or parsed.username or parsed.password:
                return ""
            candidate = unquote(parsed.path.lstrip("/"))
        except ValueError:
            return ""
    if _LOCAL_PATH.search(candidate):
        return ""
    return candidate if re.fullmatch(r"10\.[0-9]{4,9}/[^\s]+", candidate) else ""


def paper_metadata(item: dict, csl: dict) -> dict:
    """Return recorded title, publication date, venue, tags, and normalized DOI.

    Dates describe the selected bibliographic record, including preprints. Added,
    modified, and accessed dates are not publication dates. Venue and acceptance
    are never inferred from a DOI or from the paper's title. The returned title
    contains no blog title prefix. Missing values are empty strings or a list.
    """
    item = item if isinstance(item, dict) else {}
    data = item.get("data", item)
    data = data if isinstance(data, dict) else {}
    csl = csl if isinstance(csl, dict) else {}
    title = _clean(data.get("title")) or _clean(csl.get("title"))
    published = _date_text(data.get("date")) or _issued_date(csl.get("issued"))
    venue = next((value for field in ("conferenceName", "proceedingsTitle", "publicationTitle")
                  if (value := _clean(data.get(field)))), "")
    if not venue:
        venue = _clean(csl.get("event-title")) or _clean(csl.get("container-title"))
    tags = []
    raw_tags = data.get("tags", [])
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            value = _clean(tag.get("tag") if isinstance(tag, dict) else tag)
            if value and value not in tags:
                tags.append(value)
    return {
        "title": title,
        "published": published,
        "venue": venue,
        "tags": tags,
        "doi": _doi(data.get("DOI")) or _doi(csl.get("DOI")),
    }


def review_subtitle(value: object) -> tuple[str, str] | None:
    """Read the date and venue saved by the earlier review template."""
    match = re.fullmatch(r"논문 발표: (.+?) · 학회·게재처: (.+)", _clean(value))
    if match:
        published, venue = match.groups()
        return (published if published != "미확인" else "", venue if venue != "미확인" else "")
    return None


def review_paper_info(fields: dict, reference: dict, legacy_doi: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    published, venue = review_subtitle(fields.get("subtitle")) or ("", "")
    recorded = paper_metadata({}, reference)
    venue = _clean(fields.get("paper_venue")) or venue or recorded["venue"]
    published = _date_text(fields.get("paper_date")) or published or recorded["published"]
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}(?:-[0-9]{2})?", published) and _date_text(published):
        year, month, *day = published.split("-")
        published = " ".join([*(str(int(part)) for part in day), month_abbr[int(month)], year])

    doi = legacy_doi or recorded["doi"]
    doi_url = f"https://doi.org/{quote(doi, safe='/')}" if doi else ""
    paper_url = _url(fields.get("paper_url")) or doi_url or reference.get("URL")
    links = []
    for label, url in (("Paper", paper_url), ("Page", fields.get("paper_page")),
                       ("GitHub", fields.get("paper_github"))):
        if target := _url(url):
            links.append((label, target))

    affiliations = fields.get("paper_affiliations", [])
    if isinstance(affiliations, str):
        affiliations = [affiliations]
    institutions = []
    if isinstance(affiliations, list):
        institutions = list(dict.fromkeys(value for name in affiliations if (value := _clean(name))))
    lines = [", ".join(csl_author_names(reference)), " | ".join(institutions), published]
    return venue, links, list(filter(None, lines))
