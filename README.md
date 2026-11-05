# Doyunamic · AI Engineering Notes

LLM, RAG, Agent 논문을 한국어로 리뷰하는 개인 블로그입니다. Quarto로 웹페이지를 만들고 GitHub Pages에 게시합니다.

- 블로그: https://doyunamic-kwon.github.io
- 저장소: https://github.com/Doyunamic-Kwon/doyunamic-kwon.github.io
- 작성자: Doyunamic
- 검증한 Quarto 버전: 1.11.9

## 처음 살펴볼 파일

| 파일 | 역할 |
|---|---|
| `index.qmd` | 홈 화면 |
| `reviews.qmd` | 논문 리뷰 목록과 주제별 필터 |
| `about.qmd` | 소개 페이지 |
| `review-guide.qmd` | 공개된 리뷰 작성 가이드와 수식·코드·인용 예시 |
| `templates/paper-review/index.qmd` | 복사해서 사용하는 리뷰 템플릿 |
| `_quarto.yml` | 블로그 제목·주소·메뉴 설정 |
| `styles/site.css` | 디자인과 모바일 화면 설정 |
| `docs/` | Quarto가 생성한 공개 웹사이트 |

`docs/`는 자동 생성됩니다. 글과 디자인은 원본 파일을 수정한 뒤 다시 생성하세요.

## 새 리뷰 작성

macOS에서는 **새 글 만들기.command**를 열고 제목, 짧은 영문 주소, 주제를 입력하세요. 새 글은 `posts/날짜-영문주소/index.qmd`에 만들어집니다.

터미널에서도 같은 작업을 할 수 있습니다.

```bash
python3 scripts/blog.py new rag-basics --title "논문 제목 — 핵심 질문" --category RAG
```

생성된 `index.qmd`를 VS Code 등의 편집기로 열고 대괄호 내용을 실제 내용으로 바꾸세요. 사용하지 않는 선택 항목은 지워도 됩니다.

글의 위쪽에는 제목, 설명, 주제, 발행일, 수정일을 적는 설정이 있습니다. 완성한 글은 `draft: true`를 `draft: false`로 바꾸세요.

`draft: true`인 글은 공개 웹사이트의 본문·목록·검색·RSS에서 제외됩니다. Quarto 미리보기에서는 초안을 볼 수 있습니다. 공개 저장소에 올린 원본 파일은 초안도 저장소에서 읽을 수 있습니다.

## 미리보기와 게시

**미리보기.command**를 열면 브라우저에서 글과 디자인을 확인할 수 있습니다. 작성 중인 내용을 저장하면 미리보기가 갱신됩니다. 미리보기 종료는 해당 창에서 `Control + C`를 누릅니다.

**게시하기.command**는 웹사이트를 다시 생성하고, 변경 사항을 GitHub에 올립니다. GitHub Pages가 해당 파일을 반영하면 공개 블로그가 갱신됩니다.

터미널에서 사용할 명령은 다음과 같습니다.

```bash
python3 scripts/blog.py preview
python3 scripts/blog.py build
python3 scripts/blog.py publish
```

게시 전에 논문의 주장과 자신의 해석이 구분되는지, 수치의 비교 조건과 출처가 있는지, 그림·코드 링크가 열리는지 확인하세요.

## 수식·코드·참고문헌

수식은 `$...$` 또는 `$$...$$`로 작성합니다. 표시 예시는 공개된 리뷰 작성 가이드에서 확인할 수 있습니다.

코드는 `python` 등의 언어 이름을 사용한 코드 블록으로 표시하세요. 이 블로그는 문서 생성 시 코드 실행을 비활성화했습니다.

자동 인용을 쓰려면 새 글 폴더의 `references.bib`를 실제로 참조한 논문의 서지정보로 수정하세요. 글 위쪽에서 `# bibliography: references.bib`의 첫 `#`를 지우고, 본문에 `[@인용키]`를 넣으면 참고문헌이 연결됩니다.

기본 참고문헌 파일의 RAG 논문은 표시 방법을 설명하기 위한 예시입니다. 해당 논문을 실제로 참조할 때 사용하세요.

## 다른 컴퓨터에서 이어서 사용

[Quarto 공식 다운로드](https://quarto.org/docs/download/)에서 Quarto를 설치하세요. Python 3.9 이상과 Git도 필요합니다. Windows에서는 `.command` 대신 위의 Python 명령을 사용하세요.

이 작업 폴더에서는 함께 준비한 Quarto 실행 파일을 관리 도구가 자동으로 찾습니다. 폴더를 옮기거나 저장소를 새로 내려받았을 때에는 Quarto를 설치하거나 `QUARTO_BIN`에 실행 파일 경로를 지정하세요.

GitHub Pages의 게시 설정은 **Deploy from a branch → main → /docs**입니다. Quarto 공식 문서의 `docs` 폴더 게시 방식을 사용합니다. 별도 서버나 유료 구독은 필요하지 않습니다.

소개 내용은 `about.qmd`에서 바꿀 수 있습니다. LinkedIn 주소가 정해지면 소개 페이지에 추가하세요.

