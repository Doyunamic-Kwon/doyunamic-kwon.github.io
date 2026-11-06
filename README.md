# Doyunamic

LLM, RAG, Agent 논문을 한국어로 리뷰하는 개인 블로그입니다. Zotero에서 논문을 관리하고 Obsidian에서 리뷰를 작성한 뒤 Quarto와 GitHub Pages로 게시합니다.

- 블로그: https://doyunamic-kwon.github.io/
- 저장소: https://github.com/Doyunamic-Kwon/doyunamic-kwon.github.io
- 작성자: Doyunamic
- 확인한 환경: Zotero 10.0.7, Obsidian 1.12.7, Quarto 1.11.9

## 이 컴퓨터에서 시작

Obsidian WIKI의 **Blog → 블로그 작성 안내**를 열면 각 작업을 실행하는 링크와 사용 방법이 있습니다. BLOG 폴더의 `.command` 파일을 열어도 같은 작업을 할 수 있습니다.

| 파일 | 수행하는 일 |
|---|---|
| `Zotero 가져오기.command` | 논문을 선택하고 서지정보·메모·PDF의 텍스트 주석을 Obsidian으로 가져오기 |
| `새 글 만들기.command` | Zotero 논문과 연결된 리뷰 또는 빈 리뷰를 Obsidian에 만들기 |
| `미리보기.command` | 선택한 리뷰를 별도 임시 복사본에서 미리 보기 |
| `Obsidian 가져오기.command` | 공개를 선택한 리뷰와 필요한 그림을 블로그로 가져오기 |
| `게시하기.command` | 공개 리뷰 반영, 사이트 생성, GitHub 업로드 |
| `연결 확인.command` | Zotero 연결과 Obsidian 작성 폴더 확인 |

## 글을 쓰고 게시하는 순서

1. Zotero를 열고 `새 글 만들기.command`에서 논문을 고릅니다. Zotero에서 가져온 읽기 자료는 Literature에, 직접 쓸 리뷰는 Reviews에 만들어집니다.
2. Obsidian Reviews에서 질문 하나와 잠정적인 답을 먼저 쓰고, 논문의 근거를 확인하며 설명을 고칩니다.
3. `미리보기.command`에서 리뷰를 선택해 수식·그림·참고문헌을 확인합니다. 이 작업은 GitHub에 글을 올리지 않습니다.
4. 공개할 리뷰의 `blog_publish`를 `true`로 바꾸고 `게시하기.command`를 실행합니다.

논문을 선택하면 제목은 `[논문리뷰]:실제 논문명`으로 자동 생성합니다. 제목 아래에는 Zotero의 발표 날짜 또는 연도와 학회·게재처를 표시하고, DOI를 클릭할 수 있는 링크로 넣습니다. Zotero에 없는 정보는 ‘미확인’으로 표시하며 블로그 게시일을 논문 발표일로 사용하지 않습니다.

태그는 선택한 주제와 해당 Zotero 항목의 태그를 합쳐 중복을 제거합니다. 작성 중에는 Obsidian의 `title`, `subtitle`, `categories`와 본문의 DOI를 수정할 수 있습니다.

`blog_slug`는 글 주소의 마지막 부분입니다. 예를 들어 `rag-basics`이면 `/posts/rag-basics/`로 게시됩니다. 이미 게시한 글의 주소를 바꾸면 예전 링크가 끊길 수 있습니다.

## 개인 메모와 공개 리뷰

Obsidian Vault는 이 공개 저장소 밖에 있습니다. Vault의 Literature, Templates, 안내문, 설정과 일반 메모는 이 저장소에 복사하지 않습니다.

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

그림은 `![[그림.png]]` 또는 `![그림 설명](../Assets/그림.png)`로 연결합니다. 해당 그림만 복사하고, 공개 파일 이름은 그림 내용의 hash로 정합니다.

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
| `templates/paper-review/index.qmd` | 기존 Quarto용 상세 리뷰 템플릿 |
| `scripts/zotero_client.py` | Zotero의 선택 항목을 읽는 연결 기능 |
| `scripts/paper_metadata.py` | 논문 제목·발표 시기·게재처·태그·DOI 정리 |
| `scripts/publishing.py` | 리뷰·그림·링크·인용을 공개용 파일로 변환 |
| `scripts/blog.py` | 작성·미리보기·게시 작업 |
| `_quarto.yml`, `styles/` | 웹사이트와 디자인 설정 |
