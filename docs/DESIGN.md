# 과제 이력 관리 도구 — 설계 문서 (v0.1)

작성일: 2026-09-01 · 상태: 설계 확정 대기

---

## 1. 배경과 문제 정의

현재 팀의 과제별 수행 이력을 Obsidian 등 외부 클라우드 기반 마크다운 도구로 관리하고 있으나 다음 한계가 있다.

| 문제 | 영향 |
|---|---|
| 파일 첨부가 사실상 불가 | 실험 데이터(xlsx), 보고서 초안(docx/pptx), 참고 논문(PDF)을 별도 위치에 보관 → 이력과 자료가 분리됨 |
| 이미지 첨부/붙여넣기 불편 | 스크린샷 기반 기록(계측 화면, 그래프)이 누락되거나 외부 링크로 관리됨 |
| 과제 단위 관리 정보 부재 | 상태·마감일·분류를 문서 본문에 수기로 적어야 하고 목록에서 한눈에 안 보임 |
| 이력 취합 어려움 | 보고 시점에 과제 전체 이력을 하나로 묶어 내보내기 곤란 |

**목표**: 마크다운의 가벼움과 이식성은 유지하면서, 첨부 파일·이미지를 이력과 같은 자리에 붙이고, 과제 단위로 진행 상황을 조회·검색·내보내기 할 수 있는 웹 기반 도구를 만든다.

---

## 2. 확정된 전제 조건

| 항목 | 결정 |
|---|---|
| 실행 환경 | **로컬 우선** (localhost 단독 실행), 이후 사내 서버 확장 가능하도록 구조만 미리 확보 |
| 저장 방식 | **파일시스템(.md + 첨부) + SQLite 메타/인덱스 DB** |
| 사용 범위 | **1인 사용** (인증 없음, 동시 편집 충돌 처리 불필요) |
| 기술 스택 | **Python / FastAPI + SQLite** |
| 문서 구조 | 과제 1건 = **개요 문서 1개 + 날짜별 진행일지 N개**, 단 **전체를 하나의 긴 md로 다운로드** 가능해야 함 |
| 첨부 유형 | 이미지 붙여넣기(스크린샷), 오피스 문서(xlsx/docx/pptx), PDF/논문 자료 |
| 과제 목록 표시 정보 | 상태 / 기간·마감일 / 분류 태그·과제 그룹 / 최근 업데이트 일시 |

---

## 3. 설계 원칙

1. **마크다운 파일이 진실의 원천(Source of Truth)이다.**
   DB는 검색·필터를 위한 파생 인덱스일 뿐이며 언제든 파일에서 전부 재생성할 수 있어야 한다. 도구를 쓰지 않게 되더라도 데이터는 폴더 째로 남는다.
2. **첨부는 상대 경로로 저장한다.**
   `![](assets/2026-09-01/screenshot-01.png)` 형태로 저장하여 Obsidian·VS Code·GitHub 등 어떤 마크다운 뷰어에서도 이미지가 그대로 보인다. (해시 기반 중앙 저장소 방식은 이식성을 잃으므로 채택하지 않음 — 5.3 참조)
3. **로컬 단독이지만 서버 확장을 막지 않는다.**
   저장소 접근은 storage 계층 뒤로 감추고, 인증이 들어갈 자리(의존성 주입 지점)만 비워 둔다. 지금은 구현하지 않는다.
4. **외부 편집과 공존한다.**
   사용자가 Obsidian이나 편집기로 같은 폴더를 직접 수정할 수 있다고 가정하고, 파일 변경 감지 → 재인덱싱 경로를 항상 유지한다.

---

## 4. 데이터 구조

### 4.1 디렉터리 레이아웃 (Vault)

```
vault/                                  # 데이터 루트 (설정으로 위치 변경 가능)
├── projects/
│   ├── 2026-001-리튬전지-수명평가/
│   │   ├── index.md                    # 과제 개요 (메타데이터는 front matter)
│   │   ├── logs/
│   │   │   ├── 2026-09-01-실험셋업.md
│   │   │   ├── 2026-09-03-1차측정결과.md
│   │   │   └── 2026-09-10-중간보고.md
│   │   └── assets/
│   │       ├── 2026-09-03/
│   │       │   ├── 001-측정그래프.png
│   │       │   └── 002-raw-data.xlsx
│   │       └── 2026-09-10/
│   │           └── 001-중간보고초안.pptx
│   └── 2026-002-.../
├── .trash/                             # 삭제 항목 보관 (즉시 삭제하지 않음)
└── .index/
    └── index.sqlite3                   # 파생 인덱스 (삭제해도 재생성됨)
```

* 폴더명 = `{연도}-{일련번호}-{슬러그}`. 사람이 파일 탐색기에서 봐도 정렬·식별이 되도록 한다.
* 과제 ID는 폴더명 접두사(`2026-001`)로 고정하고, 제목이 바뀌어도 슬러그만 변경한다.
* 진행일지 파일명 = `YYYY-MM-DD-슬러그.md`. 같은 날 여러 건이면 `YYYY-MM-DD-2-슬러그.md`.

### 4.2 과제 개요 문서 (`index.md`)

```markdown
---
id: 2026-001
title: 리튬전지 수명평가
status: in_progress        # planned | in_progress | on_hold | done | dropped
group: 차세대전지          # 과제 그룹 (단일)
tags: [수명평가, 셀설계]    # 분류 태그 (복수)
owner: 권경락
start_date: 2026-03-02
due_date: 2026-12-20
created_at: 2026-03-02T09:12:00+09:00
updated_at: 2026-09-01T14:03:00+09:00
---

## 과제 개요
(배경, 목표, 산출물 등 고정 정보)

## 관련 링크
```

### 4.3 진행일지 (`logs/YYYY-MM-DD-*.md`)

```markdown
---
date: 2026-09-03
title: 1차 측정 결과
tags: [측정]
attachments:
  - assets/2026-09-03/001-측정그래프.png
  - assets/2026-09-03/002-raw-data.xlsx
---

오늘 셀 3종에 대해 1차 측정을 진행함.

![측정그래프](assets/2026-09-03/001-측정그래프.png)

원시 데이터: [raw-data.xlsx](assets/2026-09-03/002-raw-data.xlsx)
```

> `attachments` front matter는 본문에서 참조되지 않는 첨부(순수 자료 보관)도 추적하기 위한 목록이다. 본문에 삽입된 첨부는 인덱싱 시 자동으로 여기에 병합된다.

### 4.4 SQLite 인덱스 스키마

```sql
CREATE TABLE project (
  id            TEXT PRIMARY KEY,        -- '2026-001'
  dir_name      TEXT NOT NULL UNIQUE,    -- '2026-001-리튬전지-수명평가'
  title         TEXT NOT NULL,
  status        TEXT NOT NULL,
  grp           TEXT,
  owner         TEXT,
  start_date    TEXT,
  due_date      TEXT,
  created_at    TEXT,
  updated_at    TEXT,                    -- 과제 및 하위 일지 중 최신 수정 시각
  body          TEXT,                    -- index.md 본문 (검색용)
  file_mtime    REAL                     -- 재인덱싱 판단용
);

CREATE TABLE entry (
  id            INTEGER PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  rel_path      TEXT NOT NULL,           -- 'logs/2026-09-03-1차측정결과.md'
  date          TEXT NOT NULL,
  title         TEXT NOT NULL,
  body          TEXT,
  created_at    TEXT,
  updated_at    TEXT,
  file_mtime    REAL,
  UNIQUE(project_id, rel_path)
);

CREATE TABLE attachment (
  id            INTEGER PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  entry_id      INTEGER REFERENCES entry(id) ON DELETE SET NULL,
  rel_path      TEXT NOT NULL,           -- 'assets/2026-09-03/001-측정그래프.png'
  orig_name     TEXT NOT NULL,
  mime          TEXT,
  size_bytes    INTEGER,
  sha256        TEXT,                    -- 중복 감지용(저장 위치는 상대경로 유지)
  created_at    TEXT,
  UNIQUE(project_id, rel_path)
);

CREATE TABLE tag (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE project_tag (project_id TEXT, tag_id INTEGER, PRIMARY KEY(project_id, tag_id));
CREATE TABLE entry_tag   (entry_id INTEGER, tag_id INTEGER, PRIMARY KEY(entry_id, tag_id));

-- 전문 검색 (한국어 대응: unicode61 + trigram 보조)
CREATE VIRTUAL TABLE search_fts USING fts5(
  kind, ref_id UNINDEXED, project_id UNINDEXED, title, body,
  tokenize = "trigram"
);
```

> **한국어 검색**: FTS5 기본 토크나이저는 한국어 형태소를 나누지 못한다. 별도 형태소 분석기(konlpy 등) 의존성을 추가하지 않고, `trigram` 토크나이저로 부분 문자열 검색을 지원한다. 수천 건 규모의 개인 vault에서는 충분하며, 성능이 문제되면 그때 대체한다.

---

## 5. 핵심 기능 설계

### 5.1 화면 구성

| 화면 | 내용 |
|---|---|
| **과제 목록 / 보드** | 기본 진입 화면. 상태별 칸반 보드 ↔ 테이블 뷰 전환. 컬럼: 제목, 상태, 그룹, 태그, 마감일(D-day 배지), 최근 업데이트. 필터: 상태·그룹·태그·기간, 정렬: 최근 업데이트순(기본)/마감일순 |
| **과제 상세** | 상단에 개요(index.md) 렌더링 + 메타 편집 패널, 하단에 진행일지 타임라인(최신순). 각 일지는 접기/펼치기, 인라인 편집 진입 |
| **일지 편집기** | 좌: CodeMirror 마크다운 에디터 / 우: 실시간 미리보기. 이미지 붙여넣기·드래그앤드롭 업로드, 첨부 목록 사이드바 |
| **검색** | 전체 과제 통합 검색(제목+본문+첨부 파일명), 결과에서 과제/일지로 이동 |
| **내보내기** | 과제 단위 단일 md / zip / HTML 다운로드 |

### 5.2 첨부 업로드 흐름

```
[에디터에서 Ctrl+V 또는 드래그]
        │
        ▼
POST /api/entries/{entry_id}/attachments  (multipart)
        │
        ├─ 확장자·MIME 화이트리스트 검증, 용량 상한 확인 (기본 50MB)
        ├─ 파일명 정규화 (경로 traversal 차단, 순번 접두사 부여)
        ├─ vault/projects/{proj}/assets/{일지날짜}/{NNN}-{이름} 로 저장
        ├─ sha256 계산 → 같은 과제 내 동일 파일이면 기존 경로 재사용(중복 저장 방지)
        └─ attachment 레코드 생성
        │
        ▼
응답: { rel_path, markdown_snippet }
        │
        ▼
에디터가 커서 위치에 스니펫 삽입
   이미지 → ![이름](assets/…)   그 외 → [이름](assets/…)
```

* **미리보기 정책**: 이미지는 인라인 렌더링(썸네일 캐시 생성), PDF는 브라우저 내장 뷰어로 새 탭, 오피스 문서는 다운로드 링크 + 아이콘 표시(서버 측 변환 없음).
* **고아 파일 정리**: 어떤 문서에서도 참조되지 않는 assets 파일은 재인덱싱 시 표시만 하고 자동 삭제하지 않는다. 사용자가 "정리" 메뉴에서 확인 후 `.trash/`로 이동시킨다.

### 5.3 채택하지 않은 대안 — 중앙 첨부 저장소

`attachments/ab/cd/<sha256>.png` 형태의 콘텐츠 주소 저장은 중복 제거에 유리하지만, md 파일을 외부 도구로 열었을 때 이미지가 깨지고 사람이 파일 탐색기에서 자료를 찾을 수 없다. 이식성이 이 도구의 핵심 가치이므로 **과제 폴더 내 상대경로 저장**을 택하고, 중복 제거는 같은 과제 내 sha256 비교 수준으로 한정한다.

### 5.4 단일 md 내보내기

과제 상세 → "전체 이력 다운로드". 개요 + 모든 진행일지를 날짜 오름차순으로 병합한다.

```
GET /api/projects/{id}/export?format=md&assets=zip|inline|link
```

| 옵션 | 결과 |
|---|---|
| `assets=zip` (기본) | `2026-001-리튬전지-수명평가.zip` = 병합된 `과제명.md` + `assets/` 폴더. 상대경로가 그대로 유효 |
| `assets=inline` | 단일 `.md` 하나만. 이미지는 base64 data URI로 인라인, 비이미지 첨부는 파일명만 각주로 표기 |
| `assets=link` | 단일 `.md` 하나만. 첨부 링크는 로컬 서버 URL로 치환 (도구를 계속 쓰는 전제) |

병합 결과 구조:

```markdown
# 리튬전지 수명평가
> 상태: 진행중 · 기간: 2026-03-02 ~ 2026-12-20 · 그룹: 차세대전지 · 태그: 수명평가, 셀설계

## 과제 개요
(index.md 본문)

---
# 수행 이력

## 2026-09-01 실험 셋업
...
## 2026-09-03 1차 측정 결과
...
```

추가로 `format=html`(단일 HTML, 이미지 인라인 — 보고용 공유에 편리), `format=zip`(원본 파일 구조 그대로 백업)을 제공한다.

### 5.5 외부 편집 동기화

* 앱 기동 시 vault 전체 스캔 → `file_mtime` 비교로 변경분만 재인덱싱.
* 실행 중에는 `watchdog`으로 vault 감시, 변경 파일만 증분 인덱싱(디바운스 500ms).
* `POST /api/reindex`로 전체 재구축 가능. DB를 지워도 데이터 손실이 없다.

---

## 6. API 설계 (초안)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/projects` | 목록. `?status=&group=&tag=&q=&sort=updated\|due&order=` |
| POST | `/api/projects` | 과제 생성 (폴더 + index.md 생성) |
| GET | `/api/projects/{id}` | 개요 + 일지 목록 요약 |
| PATCH | `/api/projects/{id}` | 메타 수정 → front matter 재작성 |
| POST | `/api/projects/{id}/archive` | `.trash/`로 이동 |
| GET | `/api/projects/{id}/entries` | 진행일지 목록 |
| POST | `/api/projects/{id}/entries` | 일지 생성 |
| GET/PATCH/DELETE | `/api/entries/{entry_id}` | 일지 조회/수정/삭제 |
| POST | `/api/entries/{entry_id}/attachments` | 첨부 업로드(multipart) |
| GET | `/api/attachments/{id}` | 원본 다운로드 |
| GET | `/api/attachments/{id}/thumb` | 이미지 썸네일 |
| DELETE | `/api/attachments/{id}` | 첨부 삭제(`.trash/` 이동) |
| GET | `/api/search?q=` | 통합 검색 |
| GET | `/api/tags`, `/api/groups` | 필터용 목록 |
| GET | `/api/projects/{id}/export` | 내보내기 (5.4) |
| POST | `/api/reindex` | 전체 재인덱싱 |
| GET | `/api/health` | 상태 확인 |

정적 파일 서빙: `/files/{project_dir}/{rel_path}` — vault 경로를 벗어나는 요청은 정규화 후 거부.

---

## 7. 기술 스택 및 저장소 구조

| 영역 | 선택 | 근거 |
|---|---|---|
| 백엔드 | FastAPI + Uvicorn | 요청 스택. 파일 업로드·정적 서빙·OpenAPI 문서 기본 제공 |
| DB | SQLite (WAL) + FTS5 | 설치 불필요, 단독 사용에 충분 |
| 마크다운 파싱 | `python-frontmatter` + `markdown-it-py` | front matter 왕복(round-trip) 보존 |
| 파일 감시 | `watchdog` | 외부 편집 동기화 |
| 이미지 처리 | `Pillow` | 썸네일 생성 |
| 프론트엔드 | Vite + React + TypeScript | 에디터/보드 UI 구성 용이 |
| 에디터 | CodeMirror 6 (markdown) | 붙여넣기 이벤트 후킹이 쉬움, 가벼움 |
| 렌더링 | markdown-it + highlight.js | 백엔드와 동일 렌더링 규칙 |
| 배포 | `uv`/venv + 단일 실행 스크립트 (추후 Docker) | 로컬 실행 우선 |

```
md_mgmt_tool/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 엔트리, 정적 서빙
│   │   ├── config.py            # vault 경로, 용량 상한 등 설정
│   │   ├── db.py                # 커넥션, 마이그레이션
│   │   ├── schemas.py           # Pydantic 모델
│   │   ├── vault/
│   │   │   ├── paths.py         # 경로 계산 & traversal 방어
│   │   │   ├── markdown.py      # front matter 읽기/쓰기
│   │   │   ├── indexer.py       # 스캔 & 증분 인덱싱
│   │   │   └── watcher.py
│   │   ├── api/                 # projects / entries / attachments / search / export
│   │   └── services/            # attachments.py, export.py, thumbnails.py
│   └── tests/
├── frontend/
│   └── src/                     # pages / components / api client
├── docs/DESIGN.md
├── vault/                       # 기본 데이터 위치 (.gitignore)
└── run.sh                       # 백엔드+프론트 동시 기동
```

---

## 8. 개발 마일스톤

| 단계 | 범위 | 완료 기준 |
|---|---|---|
| **M0. 스캐폴딩** | FastAPI + Vite 기동, vault 설정, SQLite 초기화 | `run.sh` 한 번으로 빈 화면이 뜬다 |
| **M1. 과제·일지 CRUD** | 과제 생성/목록/상세, 일지 작성·편집, front matter 왕복, 인덱싱 | 브라우저에서 만든 문서가 파일 탐색기에도 정상적인 md로 보인다 |
| **M2. 첨부 (핵심 가치)** | 이미지 붙여넣기·드래그 업로드, 오피스/PDF 첨부, 썸네일, 다운로드, 고아 파일 정리 | 스크린샷 Ctrl+V → 즉시 미리보기, Obsidian으로 열어도 이미지가 보인다 |
| **M3. 관리 정보** | 상태 보드/테이블, 태그·그룹·기간 필터, D-day, 통합 검색(FTS5) | 목록 화면에서 상태·마감·태그·최근 업데이트로 즉시 정렬·필터 |
| **M4. 내보내기 & 백업** | 단일 md 병합(zip/inline/link), HTML, 전체 zip 백업 | 보고 직전 과제 이력을 md 한 개로 받아 그대로 붙여넣을 수 있다 |
| **M5. 서버 확장 (선택)** | Docker 이미지, 간단 인증, 다중 사용자 대비 잠금 | 사내 서버에 올려 팀원이 조회 가능 |

M1~M2까지가 현재 불편의 90%를 해소하는 최소 유용 제품(MVP)이다.

---

## 9. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| vault를 외부 도구로 동시 편집하며 덮어쓰기 | 저장 전 `file_mtime` 비교 → 변경 감지 시 사용자에게 알리고 덮어쓰기 여부 확인 |
| 첨부 누적으로 저장소 비대화 | 과제별 용량 표시, 업로드 상한(기본 50MB/건), 중복 파일 감지 |
| 백업 부재 | vault 폴더를 그대로 복사하면 완전 백업. 선택적으로 vault를 git 저장소로 두고 커밋 자동화 검토 |
| 한국어 전문 검색 품질 | trigram으로 시작, 부족하면 형태소 분석기 도입 |
| 경로 traversal / 파일명 충돌 | 모든 경로를 vault 루트 기준으로 정규화 후 검증, 파일명은 순번 접두사로 유일성 확보 |

---

## 10. 확정 필요 사항 (구현 착수 전)

1. **vault 기본 위치** — 예: `~/Documents/과제이력` (OneDrive/사내 동기화 폴더 안에 두면 자동 백업 효과)
2. **기존 Obsidian 문서 이관** — 지금 쓰는 노트를 가져올지, 새로 시작할지. 가져온다면 폴더 구조 샘플 필요
3. **첨부 용량 상한** — 기본 50MB로 제안. 실제 첨부하는 xlsx/PDF 크기에 맞춰 조정
4. **과제 상태 값** — `계획 / 진행중 / 보류 / 완료 / 중단` 5단계로 제안. 실제 업무 용어에 맞게 확정 필요
5. **과제 그룹 체계** — 그룹을 단일 값으로 둘지, 계층(대분류/중분류)으로 둘지
