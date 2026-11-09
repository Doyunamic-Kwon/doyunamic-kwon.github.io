# Doyunamic

LLM, RAG, Agent 논문을 한국어로 리뷰하는 개인 블로그입니다. Zotero에서 논문을 관리하고 Obsidian에서 리뷰를 작성한 뒤 Quarto와 GitHub Pages로 게시합니다.

- 블로그: https://doyunamic-kwon.github.io/
- 저장소: https://github.com/Doyunamic-Kwon/doyunamic-kwon.github.io
- 작성자: Doyunamic
- 확인한 환경: Zotero 10.0.7, Obsidian 1.12.7, Quarto 1.11.9

## 이 컴퓨터에서 시작

Obsidian WIKI의 **Blog → 블로그 작성 안내**를 열면 각 작업을 실행하는 링크와 사용 방법이 있습니다. BLOG 폴더의 `.command` 파일을 열어도 같은 작업을 할 수 있습니다.

왼쪽 메뉴는 **Blog → Reviews의 폴더와 파일 구조**에서 자동으로 만듭니다. Obsidian에서 폴더를 만들거나 글을 옮긴 뒤 게시하기를 실행하면 반영됩니다. 별도 분류 문서는 사용하지 않습니다.

`blog_publish: true`로 공개를 선택한 글과 그 글이 들어 있는 폴더만 메뉴에 나타납니다. 파일 이름은 메뉴의 글 이름이 되고, 노트의 `title`은 글 본문의 제목이 됩니다. 폴더나 파일 이름을 바꾸어도 `blog_slug`를 유지하면 글 주소는 유지됩니다. Zotero 태그와 `categories`는 폴더 구조와 별개로 글에 표시됩니다.

새 리뷰를 만들 때에는 기존 저장 폴더를 고르거나 **0. 새 폴더 만들기**에서 `Knowledge Graphs/RAG`처럼 경로를 입력할 수 있습니다. 폴더는 앞에, 글은 뒤에 이름순으로 표시합니다. 공개 글이 없는 폴더와 숨김 폴더는 메뉴에 표시하지 않습니다.

| 파일 | 수행하는 일 |
|---|---|
| `Zotero 가져오기.command` | 논문을 선택하고 서지정보·메모·PDF의 텍스트 주석을 Obsidian으로 가져오기 |
| `새 글 만들기.command` | Zotero 논문과 연결된 리뷰 또는 빈 리뷰를 Obsidian에 만들기 |
| `미리보기.command` | 선택한 리뷰를 별도 임시 복사본에서 미리 보기 |
| `게시하기.command` | 공개 리뷰 반영, 사이트 생성, GitHub 업로드 |
| `연결 확인.command` | Zotero 연결과 Obsidian 작성 폴더 확인 |

## 글을 쓰고 게시하는 순서

1. Zotero를 열고 `새 글 만들기.command`에서 논문을 고릅니다. Zotero에서 가져온 읽기 자료는 Literature에, 직접 쓸 리뷰는 Reviews에 만들어집니다.
2. Obsidian Reviews에서 질문 하나와 잠정적인 답을 먼저 쓰고, 논문의 근거를 확인하며 설명을 고칩니다.
3. `미리보기.command`에서 리뷰를 선택해 수식·그림·참고문헌을 확인합니다. 이 작업은 GitHub에 글을 올리지 않습니다.
4. 공개할 리뷰의 `blog_publish`를 `true`로 바꾸고 `게시하기.command`를 실행합니다.

논문을 선택하면 제목은 `[논문리뷰] 실제 논문명`으로 자동 생성합니다. 제목 아래에는 학회·링크, 저자, 소속, 논문 날짜를 순서대로 표시합니다. `Paper`는 DOI 또는 Zotero에 등록된 논문 링크를 사용합니다.

새 리뷰는 Zotero의 DOI나 arXiv ID를 기준으로 공개 서지 기록과 논문을 조회합니다. 논문의 소속 표기를 우선하고 `Page`는 확인된 프로젝트 페이지 또는 출판 페이지를 사용합니다. 조회할 수 없는 항목은 빈 채로 리뷰를 만듭니다.

학회·날짜·소속은 리뷰 속성의 `paper_venue`, `paper_date`, `paper_affiliations`에서 수정할 수 있습니다. `Paper`, `Page`, `GitHub` 링크는 `paper_url`, `paper_page`, `paper_github`에서 수정하세요.

태그는 저장한 폴더 이름과 해당 Zotero 항목의 태그를 합쳐 중복을 제거합니다. Reviews에 바로 저장하면 Zotero 태그를 사용합니다. 작성 중에는 Obsidian의 `title`과 `categories`를 수정할 수 있습니다.

`blog_slug`는 글 주소의 마지막 부분입니다. 예를 들어 `rag-basics`이면 `/posts/rag-basics/`로 게시됩니다. 이미 게시한 글의 주소를 바꾸면 예전 링크가 끊길 수 있습니다.

## 개인 메모와 공개 리뷰

Obsidian Vault는 이 공개 저장소 밖에 있습니다. Vault의 Literature, 안내문, 설정과 일반 메모는 이 저장소에 복사하지 않습니다.

Reviews에서 `blog_publish: true`로 선택한 글과 그 글이 사용하는 그림만 가져옵니다. 원본 파일 대신 공개에 필요한 metadata와 본문으로 새 Markdown 파일을 만듭니다.

`%% ... %%`로 감싼 Obsidian 개인 메모와 HTML 주석은 공개 복사본에서 제외합니다. 개인 노트로 연결되는 링크는 주석 안에 두세요. 공개 본문에서 다른 Obsidian 리뷰로 연결할 때에는 연결 대상도 공개를 선택해야 합니다.

공개를 철회하려면 원본 리뷰의 `blog_publish`를 false로 바꾸고 게시하기를 실행하세요. 사이트의 글과 관련 그림은 제거됩니다. 이미 public 저장소에 올린 과거 내용은 Git history에 남을 수 있습니다.

가져온 `posts/`의 복사본은 자동 생성됩니다. 직접 수정한 복사본이 있으면 가져오기를 중단하므로, 변경 내용을 Obsidian 원본에 반영하세요.

## Zotero 읽기 자료와 인용

Zotero의 Settings → Advanced → **Allow other applications on this computer to communicate with Zotero**가 켜져 있어야 합니다. 내장 Local API를 사용하며, 연결 주소는 이 컴퓨터의 `127.0.0.1:23119`입니다.

가져온 읽기 자료에서 Zotero의 논문·메모·PDF 주석 위치를 다시 열 수 있습니다. 같은 논문을 다시 가져오면 가져온 구간만 갱신하고 ‘내 메모’ 아래에 직접 적은 내용은 보존합니다.

인용은 `[@zotero-항목키]` 형식입니다. 글에 인용한 논문만 Zotero에서 CSL JSON으로 가져와 해당 글의 `references.json`으로 저장합니다. 참고문헌에는 공개에 필요한 서지정보만 남기며, 개인 메모·태그·첨부파일 경로는 포함하지 않습니다.

논문 인용이 있는 리뷰를 가져오거나 미리 볼 때에는 Zotero를 열어 두세요. 게시한 뒤 독자가 블로그를 읽을 때에는 Zotero가 필요하지 않습니다.

## 그림과 글 링크

그림은 리뷰와 같은 폴더나 Vault 안의 첨부 폴더에 저장하고 `![[그림.png]]` 또는 리뷰 기준 상대 경로로 연결합니다. 사용한 그림만 복사하고, 공개 파일 이름은 그림 내용의 hash로 정합니다.

PNG, JPEG, WebP, GIF, AVIF와 실행 요소가 없는 SVG를 지원합니다. PDF 전체나 다른 노트를 본문에 포함하는 링크는 가져오지 않습니다.

`[[다른 리뷰|표시할 이름]]`과 Markdown 링크를 지원합니다. 제목 위치를 가리키는 `[[다른 리뷰#제목]]`은 웹페이지의 해당 제목 링크로 바뀝니다. 여러 파일이 같은 이름이면 정확한 상대 경로를 적으세요.

## 다른 컴퓨터에서 연결

Python 3.10 이상, Git, [Quarto](https://quarto.org/docs/download/)가 필요합니다. 별도 Python package나 Obsidian Community plugin 설치는 필요하지 않습니다.

```bash
python3 scripts/blog.py setup --vault "/Obsidian/Vault/경로"
python3 scripts/blog.py status
```

컴퓨터별 Vault 경로와 Quarto 위치는 `.blog-local.json`에 저장하며 Git에 올리지 않습니다. Quarto가 기본 경로에 없으면 이 파일의 `quarto_path` 또는 `QUARTO_BIN`으로 지정합니다.

터미널에서도 각 작업을 실행할 수 있습니다.

```bash
python3 scripts/blog.py zotero
python3 scripts/blog.py new
python3 scripts/blog.py new paper-review --folder "Knowledge Graphs/RAG"
python3 scripts/blog.py preview
python3 scripts/blog.py sync
python3 scripts/blog.py publish
```

개발 중 검증은 다음 명령을 사용합니다.

```bash
python3 -m unittest discover -s tests -v
```

GitHub Pages는 **Deploy from a branch → main → /docs** 설정입니다. 게시 도구가 웹사이트를 새로 생성한 뒤 docs 폴더를 교체하므로 철회한 글의 HTML이 남지 않도록 합니다.

## 블로그 파일

| 파일 | 역할 |
|---|---|
| `index.qmd`, `reviews.qmd`, `about.qmd` | 홈·리뷰 목록·소개 |
| `templates/obsidian-review.md` | Obsidian용 리뷰 템플릿 |
| `scripts/zotero_client.py` | Zotero의 선택 항목을 읽는 연결 기능 |
| `scripts/paper_metadata.py`, `scripts/paper_lookup.py` | Zotero와 공개 논문에서 제목 영역의 정보 정리 |
| `scripts/obsidian_tree.py` | Obsidian의 폴더·파일 구조로 왼쪽 메뉴 생성 |
| `scripts/publishing.py` | 리뷰·그림·링크·인용을 공개용 파일로 변환 |
| `scripts/blog.py` | 작성·미리보기·게시 작업 |
| `_quarto.yml`, `styles/` | 웹사이트와 디자인 설정 |
