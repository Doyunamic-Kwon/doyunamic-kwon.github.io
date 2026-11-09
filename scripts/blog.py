#!/usr/bin/env python3
"""Zotero → Obsidian → Quarto → GitHub Pages."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from zoneinfo import ZoneInfo
from urllib.parse import quote

from obsidian_tree import FolderError, list_review_folders, resolve_review_folder
from paper_lookup import lookup_paper_fields
from paper_metadata import paper_metadata
from publishing import ObsidianPublisher, Pandoc, PublishError, meta_value, safe_inside, write_json, yaml_header
from zotero_client import ZoteroClient, ZoteroError, citation_key

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".blog-local.json"


def today() -> str:
    return dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def run(args: list[str], *, cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def output(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def config() -> dict:
    if not CONFIG.is_file():
        raise PublishError("먼저 연결 설정을 실행해 Obsidian Vault를 지정하세요.")
    try:
        data = json.loads(CONFIG.read_text())
    except (OSError, json.JSONDecodeError):
        raise PublishError("블로그의 로컬 연결 설정을 읽지 못했습니다.") from None
    if not isinstance(data, dict) or not data.get("vault"):
        raise PublishError("Obsidian Vault 경로를 연결 설정에서 확인하세요.")
    return data


def quarto() -> str:
    local = json.loads(CONFIG.read_text()) if CONFIG.is_file() else {}
    candidates = [os.environ.get("QUARTO_BIN"), shutil.which("quarto"), local.get("quarto_path"),
                  str(ROOT / ".tools/quarto/bin/quarto")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise PublishError("Quarto를 찾지 못했습니다. https://quarto.org/docs/download/ 에서 설치하세요.")


def publisher() -> ObsidianPublisher:
    return ObsidianPublisher(ROOT, config(), Pandoc(quarto()))


def setup(args: argparse.Namespace) -> None:
    if args.vault:
        values = json.loads(CONFIG.read_text()) if CONFIG.is_file() else {}
        values.update({"vault": str(Path(args.vault).expanduser().resolve()),
                       "reviews": "Blog/Reviews", "literature": "Blog/Literature", "templates": "Blog/Templates"})
        write_json(CONFIG, values)
    values = config()
    vault = Path(values["vault"]).expanduser().resolve()
    if not vault.is_dir():
        raise PublishError("Obsidian Vault 폴더를 먼저 확인하세요.")
    home = safe_inside(vault / "Blog", vault)
    for relative in ("Blog", values["reviews"], values["literature"], values["templates"], "Blog/Assets"):
        safe_inside(vault / relative, vault).mkdir(parents=True, exist_ok=True)
    identity = home / ".blog-vault-id"
    if not identity.exists():
        identity.write_text(uuid.uuid4().hex + "\n")
    template = (ROOT / "templates/obsidian-review.md").read_text()
    template_path = safe_inside(vault / values["templates"] / "논문 리뷰.md", vault)
    if not template_path.exists():
        template_path.write_text(template)
    actions = {
        "Zotero·Obsidian 연결 확인": "연결 확인.command",
        "Zotero 논문 가져오기": "Zotero 가져오기.command",
        "새 리뷰 만들기": "새 글 만들기.command",
        "선택한 리뷰 미리보기": "미리보기.command",
        "공개 선택한 리뷰 가져오기": "Obsidian 가져오기.command",
        "블로그 게시하기": "게시하기.command",
    }
    links = "\n".join(f"- [{label}]({(ROOT / name).as_uri()})" for label, name in actions.items())
    marker = "<!-- doyunamic-blog-guide -->"
    guide = f"""---
title: 블로그 작성 안내
---

{marker}

# Doyunamic 블로그 작성

이 폴더에서 논문을 읽고 리뷰를 작성합니다. 글을 공개하려면 리뷰의 `blog_publish`를 켠 뒤 게시하기를 실행하세요.

## 시작하기

{links}

파일 링크를 열면 BLOG 폴더의 작업 창이 실행됩니다. macOS에서 확인 창이 뜨면 표시된 파일 이름과 경로를 확인하세요.

## 폴더

- **Literature**: Zotero에서 가져온 논문 정보·메모·PDF 주석입니다. 새로 가져오면 가져온 구간이 갱신됩니다. 각 파일의 ‘내 메모’ 아래는 유지합니다.
- **Reviews**: 직접 쓰는 논문 리뷰입니다. Zotero 읽기 자료와 별개 파일이므로 직접 쓴 내용을 다시 가져오기로 덮어쓰지 않습니다.
- **Assets**: 리뷰에서 사용할 그림을 보관할 수 있습니다.
- **Templates**: 논문 리뷰의 기본 틀입니다.

## 폴더와 메뉴

`Blog/Reviews`의 폴더와 파일 구조가 블로그 왼쪽 메뉴가 됩니다. Obsidian에서 폴더를 만들거나 글을 옮긴 뒤 ‘블로그 게시하기’를 실행하면 반영됩니다. 별도 분류 문서는 사용하지 않습니다.

공개를 선택한 글과 그 글이 들어 있는 폴더만 메뉴에 나타납니다. 폴더 이름을 바꾸거나 글을 옮겨도 `blog_slug`를 유지하면 글 주소는 바뀌지 않습니다. 새 리뷰를 만들 때에는 저장할 폴더를 선택하거나 새 폴더를 만들 수 있습니다.

## 글을 쓰는 순서

1. Zotero를 열고 ‘Zotero 논문 가져오기’에서 논문을 선택합니다.
2. ‘새 리뷰 만들기’에서 해당 논문 또는 직접 작성할 제목을 선택합니다.
   논문을 고르면 제목은 `[논문리뷰] 실제 논문명`으로 만들어집니다. 학회·소속과 논문·프로젝트·GitHub 링크는 공개 자료에서 확인되는 항목을 채웁니다. 리뷰 속성에서 보완할 수 있습니다.
3. Reviews의 Markdown 파일에서 질문 하나와 잠정적인 답을 먼저 적고, 근거를 확인하며 설명을 고칩니다.
4. ‘선택한 리뷰 미리보기’로 수식·그림·참고문헌을 확인합니다. `blog_publish: false`인 초안도 개인 미리보기로 볼 수 있습니다.
5. 공개할 때 `blog_publish: true`로 바꾸고 ‘블로그 게시하기’를 실행합니다.

## 공개 범위

블로그로 가져오는 파일은 Reviews 안에서 `blog_publish: true`로 선택한 리뷰와 해당 리뷰에 연결한 그림입니다. Literature, 이 안내문, Templates와 Obsidian 설정은 블로그 저장소로 복사하지 않습니다.

`%% ... %%` 안의 개인 메모와 HTML 주석은 공개 복사본에서 제외됩니다. 개인 메모 링크는 주석 안에 두세요. 다른 리뷰로 연결할 때에는 연결 대상도 공개 대상으로 선택해야 합니다.

공개를 철회하려면 해당 리뷰의 `blog_publish`를 false로 바꾸고 게시하기를 실행하세요. 현재 사이트에서는 빠지지만, 이미 공개 저장소에 올린 이전 버전은 Git history에 남을 수 있습니다.

## 인용과 그림

Zotero에서 가져온 노트에는 `[@zotero-항목키]` 형식의 인용이 있습니다. 리뷰 본문에 복사하면 게시 전에 해당 논문의 서지정보만 Zotero에서 가져옵니다. 논문 인용이 있는 글을 가져오거나 미리 볼 때에는 Zotero를 열어 두세요.

그림은 `![[그림.png]]` 또는 `![그림 설명](../Assets/그림.png)`로 연결합니다. 사용한 그림만 공개 복사본에 들어갑니다. PDF 전체나 다른 노트를 본문에 포함하는 기능은 이 게시 흐름에서 사용하지 않습니다.

블로그용으로 생성한 posts 폴더의 복사본은 직접 수정하지 말고 Reviews의 원본을 수정하세요.
"""
    guide_path = home / "블로그 작성 안내.md"
    if not guide_path.exists() or marker in guide_path.read_text():
        guide_path.write_text(guide)
    print(f"Obsidian 연결 완료: {home}")
    print("Obsidian에서 ‘블로그 작성 안내’를 열어 시작하세요.")


def choose_item(key: str | None = None, *, allow_none: bool = False) -> str | None:
    if key:
        citation_key(key)
        return key
    items = ZoteroClient().list_items()
    if allow_none:
        print("0. 논문 선택 없이 직접 작성")
    for index, item in enumerate(items, 1):
        print(f"{index}. {item['title']}")
    if not items and not allow_none:
        raise PublishError("Zotero에 가져올 논문 항목이 없습니다.")
    answer = input("논문 번호: ").strip()
    if answer == "0" and allow_none:
        return None
    if not answer.isdigit() or not 1 <= int(answer) <= len(items):
        raise PublishError("목록에서 논문 번호를 선택하세요.")
    return items[int(answer) - 1]["key"]


def import_zotero(key: str) -> Path:
    values = config()
    vault = Path(values["vault"]).resolve()
    folder = safe_inside(vault / values["literature"], vault)
    folder.mkdir(parents=True, exist_ok=True)
    client = ZoteroClient()
    item = client.get_item(key)
    title = item.get("data", item).get("title", key)
    safe_title = re.sub(r'[\x00-\x1f/\\:*?"<>|]', " ", title).strip()[:100] or key
    existing = list(folder.glob(f"* - {key}.md"))
    if len(existing) > 1:
        raise PublishError("같은 Zotero 논문의 읽기 메모가 여러 개 있습니다.")
    path = safe_inside(existing[0] if existing else folder / f"{safe_title} - {key}.md", vault)
    generated = client.literature_markdown(key)
    pieces = generated.split("---", 2)
    if len(pieces) != 3:
        raise PublishError("Zotero 읽기 메모 형식을 확인하지 못했습니다.")
    start, end = "<!-- zotero-import:start -->", "<!-- zotero-import:end -->"
    block = start + "\n\n" + pieces[2].strip() + "\n\n" + end
    if path.exists():
        previous = path.read_text()
        if previous.count(start) != 1 or previous.count(end) != 1:
            raise PublishError("기존 읽기 메모의 가져오기 구간을 확인할 수 없어 덮어쓰지 않았습니다.")
        before, remainder = previous.split(start, 1)
        _, after = remainder.split(end, 1)
        rendered = before + block + after
    else:
        rendered = "---" + pieces[1] + "---\n\n" + block + "\n\n## 내 메모\n\n"
    path.write_text(rendered)
    print(f"Zotero 읽기 메모를 가져왔습니다: {path.name}")
    return path


def choose_review_folder(root: Path, supplied: str | None = None) -> Path:
    if supplied is not None:
        return resolve_review_folder(root, supplied)
    folders = list_review_folders(root)
    for index, relative in enumerate(folders, 1):
        label = "Reviews에 바로 작성" if relative == "." else relative
        print(f"{index}. {label}")
    print("0. 새 폴더 만들기")
    answer = input("저장할 폴더 번호 [기본 1]: ").strip()
    if answer == "0":
        relative = input("새 폴더 경로 (예: Knowledge Graphs/RAG): ").strip()
        if not relative:
            raise FolderError("새 폴더 이름을 입력하세요.")
        return resolve_review_folder(root, relative)
    if (answer or "1").isdigit() and 1 <= int(answer or "1") <= len(folders):
        return resolve_review_folder(root, folders[int(answer or "1") - 1])
    raise FolderError("목록에서 폴더 번호를 선택하거나 0으로 새 폴더를 만드세요.")


def ensure_unique_review_slug(reviews: Path, slug: str) -> None:
    pandoc = None
    for path in sorted(reviews.rglob("*.md")):
        if any(part.startswith('.') for part in path.relative_to(reviews).parts):
            continue
        path = safe_inside(path, reviews)
        with path.open(encoding="utf-8-sig") as source:
            first = source.readline()
            if first.strip() != "---":
                continue
            header = [first]
            for line in source:
                header.append(line)
                if sum(map(len, header)) > 65536:
                    raise PublishError("기존 리뷰의 속성 영역이 너무 큽니다. 해당 노트를 확인하세요.")
                if line.strip() in {"---", "..."}:
                    break
            else:
                continue
        if pandoc is None:
            pandoc = Pandoc(quarto())
        field = pandoc.parse(''.join(header)).get('meta', {}).get('blog_slug')
        if field and meta_value(field) == slug:
            raise PublishError("다른 폴더의 리뷰가 같은 글 주소를 사용하고 있습니다. 다른 blog_slug를 입력하세요.")


def new_post(args: argparse.Namespace) -> None:
    values = config()
    key = choose_item(args.zotero, allow_none=True) if args.zotero or not args.title else None
    note = import_zotero(key) if key else None
    paper = {}
    if key:
        client = ZoteroClient()
        item, reference = client.get_item(key), client.get_csl(key)
        paper = paper_metadata(item, reference)
    default_title = f"[논문리뷰] {paper['title']}" if paper.get("title") else ""
    title = args.title or default_title or input("리뷰 제목: ").strip()
    slug = args.slug or input("글 주소에 사용할 짧은 영문 이름 (예: rag-basics): ").strip()
    vault = Path(values["vault"]).resolve()
    reviews = safe_inside(vault / values["reviews"], vault)
    review_folder = choose_review_folder(reviews, getattr(args, "folder", None))
    category = args.category or (review_folder.name if review_folder != reviews else "")
    categories, seen_categories = [], set()
    for tag in [category, *paper.get("tags", [])]:
        tag = tag.strip()
        if tag and tag.casefold() not in seen_categories:
            categories.append(tag)
            seen_categories.add(tag.casefold())
    if not title:
        raise PublishError("리뷰 제목을 입력하세요.")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 80:
        raise PublishError("글 주소에는 소문자·숫자·하이픈을 사용하세요.")
    destination = safe_inside(review_folder / f"{slug}.md", reviews)
    if destination.exists():
        raise PublishError("같은 주소의 Obsidian 리뷰가 이미 있습니다.")
    ensure_unique_review_slug(reviews, slug)
    template = (ROOT / "templates/obsidian-review.md").read_text()
    body = template.split("---", 2)[2].lstrip()
    if key:
        doi = paper["doi"]
        doi_label = re.sub(r"([\\`*_\[\]<>|])", r"\\\1", doi)
        doi_line = f"DOI: [{doi_label}](https://doi.org/{quote(doi, safe='/')})" if doi else "DOI: 미확인"
        body = body.replace("<!-- PAPER_DOI -->", doi_line)
        body = body.replace("<!-- ZOTERO_CITATION -->", f"논문: [@{citation_key(key)}]")
        relative = note.relative_to(vault).with_suffix("").as_posix()
        body = body.replace("<!-- ZOTERO_NOTE -->", f"[[{relative}|Zotero 읽기 메모]]")
    else:
        body = body.replace("<!-- ZOTERO_CITATION -->", "").replace("<!-- ZOTERO_NOTE -->", "").replace("<!-- PAPER_DOI -->", "")
    fields = {"title": title, "description": "", "categories": categories, "date": today(),
              "date-modified": today(), "blog_publish": False, "blog_slug": slug}
    if key:
        fields["zotero_key"] = key
        published = paper["published"] or "미확인"
        venue = paper["venue"] or "미확인"
        fields["subtitle"] = f"논문 발표: {published} · 학회·게재처: {venue}"
        print("학회·소속과 논문 링크를 확인합니다.")
        fields.update(lookup_paper_fields(item, reference, paper))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml_header(fields) + body)
    print(f"\nObsidian 리뷰 초안을 만들었습니다.\n{destination}")
    print("\n미리보기로 확인한 뒤 blog_publish를 true로 바꾸면 게시할 수 있습니다.")


def choose_review(pub: ObsidianPublisher, note: str | None = None):
    if note:
        candidate = Path(note).expanduser()
        if not candidate.is_absolute():
            candidate = pub.reviews / candidate
            if not candidate.suffix:
                candidate = candidate.with_suffix(".md")
        return pub.review(candidate, allow_draft=True)
    candidates = pub.candidates(ready_only=False)
    if not candidates:
        raise PublishError("먼저 ‘새 글 만들기’에서 Obsidian 리뷰 초안을 작성하세요.")
    for index, review in enumerate(candidates, 1):
        state = "공개 선택" if review.meta.get("blog_publish") is True else "개인 초안"
        print(f"{index}. {review.meta['title']} ({state})")
    answer = input("미리 볼 리뷰 번호: ").strip()
    if not answer.isdigit() or not 1 <= int(answer) <= len(candidates):
        raise PublishError("목록에서 리뷰 번호를 선택하세요.")
    return candidates[int(answer) - 1]


def sync_reviews() -> dict:
    plan = publisher().sync()
    for slug in plan["updated"]:
        print(f"가져온 리뷰: {slug}")
    for slug in plan["removed"]:
        print(f"공개 대상에서 제외: {slug}")
    if not plan["updated"] and not plan["removed"]:
        print("공개를 선택한 새 리뷰가 없습니다.")
    return plan


def build(*, sync: bool = True, tracked_posts_only: bool = False) -> None:
    if sync:
        sync_reviews()
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="site-build-", dir=work))
    backup = None
    try:
        pub = publisher()
        sources = publishable_paths(pub)
        if tracked_posts_only:
            tracked = set(subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "-z", "HEAD"], cwd=ROOT).decode().split("\0"))
            sources = [name for name in sources if not name.startswith("posts/") or name in tracked]
        project = pub.website_project(staging / "project", sources)
        run([quarto(), "render", "--output-dir", "_site"], cwd=project)
        built = project / "_site"
        if not (built / "index.html").is_file():
            raise PublishError("생성한 홈페이지를 확인하지 못했습니다.")
        (built / ".nojekyll").touch()
        docs = ROOT / "docs"
        if docs.is_symlink():
            raise PublishError("docs 폴더가 다른 위치를 가리킵니다.")
        if docs.exists():
            backup = Path(tempfile.mkdtemp(prefix="previous-site-", dir=work)) / "docs"
            docs.rename(backup)
        built.rename(docs)
        if backup:
            shutil.rmtree(backup.parent)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


PUBLIC_ROOT = {".gitignore", ".nojekyll", "README.md", "_quarto.yml", "index.qmd", "reviews.qmd",
               "about.qmd", "review-guide.qmd", "references.bib", "새 글 만들기.command", "미리보기.command",
               "게시하기.command", "Zotero 가져오기.command", "Obsidian 가져오기.command", "연결 확인.command"}
PUBLIC_DIRS = {"assets", "styles", "includes", "templates", "scripts", "tests", "docs"}
SOURCE_ADDITIONS = {"scripts/publishing.py", "scripts/zotero_client.py", "tests/test_publishing.py",
                    "tests/test_zotero_client.py", "templates/obsidian-review.md", "scripts/paper_metadata.py",
                    "tests/test_paper_metadata.py", "tests/test_blog.py", "scripts/obsidian_tree.py",
                    "tests/test_obsidian_tree.py", "scripts/paper_lookup.py", "tests/test_paper_lookup.py"}


def publishable_paths(pub: ObsidianPublisher) -> list[str]:
    tracked = set(subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "-z", "HEAD"], cwd=ROOT).decode().split("\0")) - {""}
    untracked = set(subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")) - {""}
    indexed = set(subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=ROOT).decode().split("\0")) - {""}
    allowed = set()
    for name in tracked | untracked | indexed:
        parts = Path(name).parts
        known_source = name in tracked or name in SOURCE_ADDITIONS
        generated = parts and parts[0] == "docs"
        if name in PUBLIC_ROOT or ((known_source or generated) and parts and parts[0] in PUBLIC_DIRS and not any(p.startswith(".") for p in parts[1:])):
            allowed.add(name)
        elif name == "docs/.nojekyll" or name in {"posts/_metadata.yml", "posts/.gitkeep"}:
            allowed.add(name)
        elif parts and parts[0] == "posts":
            if name in tracked and not (ROOT / name).exists():
                allowed.add(name)
                continue
            if len(parts) >= 3:
                marker = ROOT / "posts" / parts[1] / pub.MARKER
                if marker.is_file():
                    values = json.loads(marker.read_text())
                    if name == str(marker.relative_to(ROOT)) or Path(*parts[2:]).as_posix() in values.get("files", {}):
                        allowed.add(name)
                elif name in tracked:
                    allowed.add(name)
    return sorted(allowed)


def publish() -> None:
    if Path(output(["git", "rev-parse", "--show-toplevel"])).resolve() != ROOT:
        raise PublishError("블로그 폴더 자체가 Git 저장소여야 합니다.")
    if output(["git", "branch", "--show-current"]) != "main":
        raise PublishError("게시하려면 main 브랜치로 이동하세요.")
    remote = output(["git", "remote", "get-url", "origin"])
    if not re.fullmatch(r"(?:https://github\.com/|git@github\.com:)Doyunamic-Kwon/doyunamic-kwon\.github\.io(?:\.git)?", remote, re.I):
        raise PublishError("블로그 저장소 주소를 확인하세요.")
    build()
    pub = publisher()
    allowed = publishable_paths(pub)
    staged = set(subprocess.check_output(["git", "diff", "--cached", "--name-only", "-z"], cwd=ROOT).decode().split("\0")) - {""}
    if staged - set(allowed):
        raise PublishError("게시 대상 밖의 파일이 미리 Git에 선택돼 있습니다. 해당 파일을 먼저 확인하세요.")
    if allowed:
        run(["git", "add", "--all", "--", *allowed])
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode
    if changed == 1:
        run(["git", "commit", "-m", "Connect Zotero and Obsidian review publishing"])
    elif changed != 0:
        raise PublishError("게시 변경 사항을 확인하지 못했습니다.")
    run(["git", "push", "origin", "main"])
    print("\n게시 파일을 올렸습니다. GitHub Pages에 반영되면 아래 주소에서 볼 수 있습니다.")
    print("https://doyunamic-kwon.github.io/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Doyunamic 논문 리뷰 작성과 게시")
    commands = parser.add_subparsers(dest="command", required=True)
    connect = commands.add_parser("setup", help="Obsidian 작성 폴더와 안내 준비")
    connect.add_argument("--vault")
    z = commands.add_parser("zotero", help="Zotero 논문과 메모 가져오기")
    z.add_argument("key", nargs="?")
    new = commands.add_parser("new", help="Obsidian에 리뷰 초안 만들기")
    new.add_argument("slug", nargs="?")
    new.add_argument("--title")
    new.add_argument("--category", help="추가할 태그 (메뉴는 폴더에서 생성)")
    new.add_argument("--folder", help="Reviews 안의 저장 폴더, 예: Knowledge Graphs/RAG")
    new.add_argument("--zotero")
    preview = commands.add_parser("preview", help="개인 초안을 별도 복사본으로 미리보기")
    preview.add_argument("--note")
    preview.add_argument("--prepare-only", action="store_true")
    commands.add_parser("sync", help="공개를 선택한 리뷰만 블로그로 가져오기")
    commands.add_parser("build", help="선택한 리뷰를 반영한 웹사이트 생성")
    commands.add_parser("publish", help="선택한 리뷰와 블로그를 게시")
    commands.add_parser("status", help="연결 상태와 공개할 리뷰 수 확인")
    args = parser.parse_args()
    if args.command == "setup":
        setup(args)
    elif args.command == "zotero":
        import_zotero(choose_item(args.key))
    elif args.command == "new":
        new_post(args)
    elif args.command == "sync":
        sync_reviews()
    elif args.command == "build":
        build()
    elif args.command == "publish":
        publish()
    elif args.command == "preview":
        pub = publisher()
        review = choose_review(pub, args.note)
        folder = pub.preview_project(review, publishable_paths(pub))
        if args.prepare_only:
            print(folder)
        else:
            print("개인 미리보기입니다. 이 작업으로 GitHub에 글을 올리지 않습니다.")
            run([quarto(), "preview", str(folder)])
    elif args.command == "status":
        pub = publisher()
        ZoteroClient().list_items(limit=1)
        print("Zotero 연결: 정상")
        print(f"Obsidian 작성 폴더: {pub.reviews}")
        print(f"공개를 선택한 리뷰: {len(pub.candidates())}편")


if __name__ == "__main__":
    try:
        main()
    except (PublishError, ZoteroError, FolderError) as error:
        print(f"\n{error}", file=sys.stderr)
        sys.exit(1)
    except (subprocess.CalledProcessError, KeyboardInterrupt):
        sys.exit(1)
