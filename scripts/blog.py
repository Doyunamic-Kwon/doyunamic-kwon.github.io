#!/usr/bin/env python3
"""Create a review, preview the website, or publish the rendered site."""

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
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def output(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def quarto() -> str:
    candidates = [
        os.environ.get("QUARTO_BIN"),
        shutil.which("quarto"),
        str(ROOT / ".tools/quarto/bin/quarto"),
        str(ROOT.parent.parent / "work/bin/quarto"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit(
        "Quarto를 찾지 못했습니다. https://quarto.org/docs/download/ 에서 설치한 뒤 다시 실행하세요."
    )


def new_post(args: argparse.Namespace) -> None:
    title = args.title or input("논문 리뷰 제목: ").strip()
    slug = args.slug or input("글 주소에 사용할 짧은 영문 이름 (예: rag-basics): ").strip()
    category = args.category or input("주제 [LLM / RAG / Agent, 기본 LLM]: ").strip() or "LLM"
    if not title:
        raise SystemExit("제목을 입력하세요.")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 80:
        raise SystemExit("글 주소에는 소문자·숫자·하이픈을 사용하세요. 예: rag-basics")
    today = dt.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    destination = ROOT / "posts" / f"{today}-{slug}"
    if destination.exists():
        raise SystemExit(f"이미 같은 주소의 글이 있습니다: {destination}")
    source = (ROOT / "templates/paper-review/index.qmd").read_text(encoding="utf-8")
    source = re.sub(r"^title:.*$", lambda _: f"title: {json.dumps(title, ensure_ascii=False)}", source, count=1, flags=re.M)
    source = re.sub(r"^categories:.*$", lambda _: f"categories: {json.dumps([category], ensure_ascii=False)}", source, count=1, flags=re.M)
    source = re.sub(r"^(date|date-modified):.*$", lambda match: f"{match.group(1)}: {today}", source, flags=re.M)
    destination.mkdir(parents=True)
    (destination / "index.qmd").write_text(source, encoding="utf-8")
    shutil.copyfile(ROOT / "templates/paper-review/references.bib.example", destination / "references.bib")
    print(f"\n초안을 만들었습니다.\n{destination / 'index.qmd'}")
    print("\n작성 후 draft: false로 바꾸면 웹사이트에 게시됩니다.")


def publish() -> None:
    if not (ROOT / ".git").is_dir():
        raise SystemExit("먼저 이 폴더를 GitHub 저장소와 연결하세요. README.md를 참고하세요.")
    repository_root = Path(output(["git", "rev-parse", "--show-toplevel"])).resolve()
    if repository_root != ROOT:
        raise SystemExit("블로그 폴더 자체가 Git 저장소여야 합니다.")
    branch = output(["git", "branch", "--show-current"])
    if branch != "main":
        raise SystemExit("게시하려면 먼저 main 브랜치로 이동하세요.")
    remote = output(["git", "remote", "get-url", "origin"])
    if not re.fullmatch(r"(?:https://github\.com/|git@github\.com:)Doyunamic-Kwon/doyunamic-kwon\.github\.io(?:\.git)?", remote, re.I):
        raise SystemExit("이 블로그의 GitHub 저장소 주소를 확인하세요.")
    for post in (ROOT / "posts").glob("**/*.qmd"):
        content = post.read_text(encoding="utf-8")
        front_matter = content.split("---", 2)
        if len(front_matter) < 3:
            raise SystemExit(f"글의 제목·날짜 설정을 확인하세요: {post}")
        if re.search(r"^draft:\s*true\s*$", front_matter[1], flags=re.M):
            continue
        without_comments = re.sub(r"<!--.*?-->", "", content, flags=re.S)
        if re.search(r"\[(?:논문 제목|핵심 질문|값|Dataset · split)\]", without_comments):
            raise SystemExit(f"템플릿의 빈 내용을 먼저 작성하거나 draft: true를 유지하세요: {post}")
    run([quarto(), "render"])
    (ROOT / "docs/.nojekyll").touch()
    run(["git", "add", "--all"])
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode
    if changed == 1:
        run(["git", "commit", "-m", "Update blog content and rendered site"])
    elif changed != 0:
        raise SystemExit("변경 사항을 확인하지 못했습니다.")
    run(["git", "push", "origin", "main"])
    print("\n게시 파일을 올렸습니다. GitHub Pages 반영까지 잠시 걸릴 수 있습니다.")
    print("https://doyunamic-kwon.github.io")


def main() -> None:
    parser = argparse.ArgumentParser(description="Doyunamic 블로그 관리")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="리뷰 초안 만들기")
    new.add_argument("slug", nargs="?")
    new.add_argument("--title")
    new.add_argument("--category")
    commands.add_parser("preview", help="작성 중인 글과 디자인 미리보기")
    commands.add_parser("build", help="공개할 웹사이트 생성")
    commands.add_parser("publish", help="웹사이트 생성 후 GitHub Pages에 게시")
    args = parser.parse_args()
    if args.command == "new":
        new_post(args)
    elif args.command == "preview":
        run([quarto(), "preview"])
    elif args.command == "build":
        run([quarto(), "render"])
    elif args.command == "publish":
        publish()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)

