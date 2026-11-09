"""Look up public metadata for the Zotero item selected for a new review."""

from __future__ import annotations

from html.parser import HTMLParser
from http.client import HTTPException
import json
import re
import unicodedata
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from paper_metadata import _clean, _doi, _issued_date
from zotero_client import _url


_CROSSREF = "https://api.crossref.org/works"
_ARXIV_ID = re.compile(r"(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7})(?:v[1-9]\d*)?", re.I)
_GITHUB_URL = re.compile(r"https://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)", re.I)
_PROJECT_PAGE = re.compile(
    r"\bproject (?:page|website|site)\s*(?:(?:is\s+)?(?:available\s+)?at\s+|:\s*)?"
    r"(https?://[^\s<>\[\]\"']+)", re.I,
)
_PUBLISHED_TYPES = {"journal-article", "proceedings-article"}


class _SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.netloc != urlsplit(req.full_url).netloc:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url: str) -> str:
    # Requests go only to the fixed metadata services below. Returned links are not fetched.
    try:
        request = Request(url, headers={"User-Agent": "DoyunamicPaperReview/1.0"})
        with build_opener(_SameHostRedirect()).open(request, timeout=4) as response:
            return response.read(1_500_000).decode("utf-8", errors="replace")
    except HTTPError as error:
        error.close()
        return ""
    except (OSError, HTTPException, ValueError):
        return ""


def _object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _objects(value: object) -> list[dict]:
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def _json(url: str) -> dict:
    try:
        return _object(json.loads(_fetch(url)))
    except (ValueError, RecursionError):
        return {}


def _identity(value: object) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", _clean(value)).casefold() if char.isalnum())


def _first_text(value: object) -> str:
    return _clean(value[0]) if isinstance(value, list) and value else _clean(value)


def _arxiv_id(value: object) -> str:
    text = _clean(value)
    if doi := _doi(text):
        text = doi.casefold().removeprefix("10.48550/arxiv.")
    elif text.startswith(("https://", "http://")):
        try:
            url = urlsplit(text)
            if url.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
                return ""
            _, route, identifier = url.path.split("/", 2)
            text = unquote(identifier).removesuffix(".pdf") if route in {"abs", "pdf", "html"} else ""
        except ValueError:
            return ""
    text = re.sub(r"^arxiv:\s*", "", text, flags=re.I)
    return text if _ARXIV_ID.fullmatch(text) else ""


def _arxiv_base(identifier: str) -> str:
    return re.sub(r"v\d+$", "", identifier, flags=re.I).casefold()


def _author_match(left: dict, right: dict) -> bool:
    family = _identity(left.get("family"))
    if not family or family != _identity(right.get("family")):
        return False
    given, other = _identity(left.get("given")), _identity(right.get("given"))
    return bool(given and other and (given == other or (min(len(given), len(other)) == 1 and given[0] == other[0])))


def _publication(doi: str, arxiv: str, paper: dict, authors: list[dict]) -> dict:
    title = paper["title"]
    if doi and not _arxiv_id(doi):
        work = _object(_json(f"{_CROSSREF}/{quote(doi, safe='/')}").get("message"))
        work_title = _first_text(work.get("title"))
        if _doi(work.get("DOI")).casefold() == doi.casefold() and (
            not title or not work_title or _identity(title) == _identity(work_title)
        ):
            return work
        if not arxiv:
            return {}

    if not title or not authors or not _clean(authors[0].get("family")):
        return {}
    query = urlencode({"query.bibliographic": f"{title} {_clean(authors[0]['family'])}", "rows": 6})
    matches = {}
    result = _object(_json(f"{_CROSSREF}?{query}").get("message"))
    selected_year = paper["published"][:4]
    for work in _objects(result.get("items")):
        matched_doi = _doi(work.get("DOI"))
        if not matched_doi or work.get("type") not in _PUBLISHED_TYPES:
            continue
        if _identity(_first_text(work.get("title"))) != _identity(title):
            continue
        deposited = _objects(work.get("author"))
        if len(deposited) != len(authors) or not all(_author_match(a, b) for a, b in zip(authors, deposited)):
            continue
        year = (_issued_date(work.get("published")) or _issued_date(work.get("issued")))[:4]
        if selected_year and (not year or not -1 <= int(year) - int(selected_year) <= 3):
            continue
        matches[matched_doi.casefold()] = work
    return next(iter(matches.values())) if len(matches) == 1 else {}


def _indexed_work(doi: str, title: str, arxiv: str = "") -> dict:
    fields = "doi,display_name,locations,authorships"
    work = _json(f"https://api.openalex.org/works/https://doi.org/{quote(doi, safe='/')}?select={fields}")
    if _doi(work.get("doi")).casefold() != doi.casefold():
        arxiv_locations = {_arxiv_base(_arxiv_id(location.get("landing_page_url")))
                           for location in _objects(work.get("locations"))}
        if not arxiv or _arxiv_base(arxiv) not in arxiv_locations:
            return {}
    return work if not title or _identity(work.get("display_name")) == _identity(title) else {}


class _ArxivHeader(HTMLParser):
    """Read author affiliations and the abstract, never links in the references."""

    def __init__(self):
        super().__init__()
        self.values = {"title": [], "affiliation": [], "summary": [], "journal": []}
        self.section = ""
        self.tag = ""
        self.depth = 0
        self.parts = []
        self.author_has_affiliation = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.section:
            if tag == self.tag:
                self.depth += 1
            if tag == "a" and self.section == "summary" and (href := attrs.get("href")):
                self.parts.append(f" {href} ")
            return
        classes = set((attrs.get("class") or "").split())
        if "ltx_role_author" in classes:
            self.author_has_affiliation = False
        if tag == "title":
            self.section = "title"
        elif "ltx_role_affiliation" in classes:
            self.section = "affiliation"
        elif "ltx_abstract" in classes or (tag == "blockquote" and "abstract" in classes) or (tag == "td" and "comments" in classes):
            self.section = "summary"
        elif tag == "td" and "jref" in classes:
            self.section = "journal"
        if self.section:
            self.tag, self.depth, self.parts = tag, 1, []

    def handle_endtag(self, tag):
        if self.section and tag == self.tag:
            self.depth -= 1
            if self.depth == 0:
                value = _clean("".join(self.parts))
                entries = self.values[self.section]
                if self.section == "affiliation":
                    value = value.removeprefix("Affiliation:").strip()
                    if self.author_has_affiliation and value.startswith(("and ", "of ", "for ")):
                        entries[-1] += f" {value}"
                    elif value:
                        entries.append(value)
                        self.author_has_affiliation = True
                else:
                    entries.append(value)
                self.section = ""

    def handle_data(self, data):
        if self.section:
            self.parts.append(data)


def _arxiv_header(arxiv: str, title: str, route: str) -> dict:
    parser = _ArxivHeader()
    parser.feed(_fetch(f"https://arxiv.org/{route}/{quote(arxiv, safe='/')}"))
    actual_title = re.sub(r"^\[[^\]]+\]\s*", "", _first_text(parser.values["title"]))
    return parser.values if actual_title and (not title or _identity(actual_title) == _identity(title)) else {}


def _github(value: object) -> str:
    match = _GITHUB_URL.search(value) if isinstance(value, str) else None
    if not match:
        return ""
    owner, repo = match.groups()
    repo = repo.rstrip(".").removesuffix(".git")
    return f"https://github.com/{owner}/{repo}" if repo else ""


def _project(summary: str) -> str:
    match = _PROJECT_PAGE.search(summary)
    if not match:
        return ""
    return _url(match[1].rstrip(".,;:!?()")) or ""


def _affiliations(values: list) -> list[str]:
    names = (_clean(value).removeprefix("Affiliation:").strip() for value in values)
    return list(dict.fromkeys(name for name in names if name and "@" not in name))


def lookup_paper_fields(item: dict, csl: dict, paper: dict) -> dict:
    """Fill supported review properties using the selected paper's public identifiers."""
    data = _object(item.get("data", item))
    extra = {}
    for line in str(data.get("extra", "")).splitlines():
        label, separator, value = line.partition(":")
        if separator:
            extra[label.strip().casefold()] = value.strip()
    doi, title = paper["doi"], paper["title"]
    source_url = _url(data.get("url")) or _url(csl.get("URL"))
    arxiv = next((identifier for value in (source_url, doi, data.get("archiveID"), extra.get("arxiv"))
                  if (identifier := _arxiv_id(value))), "")
    authors = _objects(csl.get("author"))
    work = _publication(doi, arxiv, paper, authors)
    indexed = {}
    if arxiv and (not work or work.get("type") == "posted-content"):
        indexed = _indexed_work(f"10.48550/arXiv.{_arxiv_base(arxiv)}", title, arxiv)
        if (linked_doi := _doi(indexed.get("doi"))) and not _arxiv_id(linked_doi):
            work = _publication(linked_doi, "", paper, authors) or work
    deposited_doi = _doi(work.get("DOI")) or doi
    if deposited_doi and not arxiv:
        indexed = _indexed_work(deposited_doi, title)
        alternatives = {_arxiv_id(location.get("landing_page_url"))
                        for location in _objects(indexed.get("locations"))} - {""}
        if len(alternatives) == 1:
            arxiv = next(iter(alternatives))
    event = _object(work.get("event"))
    venue = paper["venue"]
    if arxiv and venue.casefold().startswith("arxiv"):
        venue = ""
    venue = (venue or _clean(event.get("acronym")) or _clean(event.get("name"))
             or _first_text(work.get("container-title")))
    resource = _object(_object(work.get("resource")).get("primary"))
    publisher_page = _url(resource.get("URL"))

    html = _arxiv_header(arxiv, title, "html") if arxiv else {}
    summary = " ".join([*html.get("summary", []), str(data.get("abstractNote", "")), str(work.get("abstract", ""))])
    github = _github(extra.get("github")) or _github(summary)
    project_page = _url(extra.get("project page")) or _project(summary)
    if arxiv and (not github or not venue):
        abstract = _arxiv_header(arxiv, title, "abs")
        summary = " ".join(abstract.get("summary", []))
        github = github or _github(summary)
        project_page = project_page or _project(summary)
        venue = venue or _first_text(abstract.get("journal"))

    if github and not project_page:
        repository = github.removeprefix("https://github.com/")
        metadata = _json(f"https://api.github.com/repos/{repository}")
        project_page = _url(metadata.get("homepage"))
        github = _github(metadata.get("html_url")) or github
    affiliations = _affiliations(extra.get("affiliation", "").split("|")) or _affiliations(html.get("affiliation", []))
    if not affiliations:
        affiliations = _affiliations([affiliation.get("name") for author in _objects(work.get("author"))
                                      for affiliation in _objects(author.get("affiliation"))])
    if not affiliations:
        raw_affiliations = [author.get("raw_affiliation_strings") for author in _objects(indexed.get("authorships"))]
        affiliations = _affiliations([name for values in raw_affiliations if isinstance(values, list) for name in values])
    paper_url = f"https://doi.org/{quote(doi, safe='/')}" if doi else source_url
    if not paper_url and arxiv:
        paper_url = f"https://arxiv.org/abs/{arxiv}"
    if not paper_url and deposited_doi:
        paper_url = f"https://doi.org/{quote(deposited_doi, safe='/')}"
    page = _url(extra.get("paper page")) or project_page or publisher_page
    fields = {"paper_venue": venue, "paper_affiliations": affiliations, "paper_url": paper_url,
              "paper_page": page if page != paper_url else "", "paper_github": github}
    return {key: value for key, value in fields.items() if value}
