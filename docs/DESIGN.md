# 과제 이력 관리 도구 — 설계 문서 (v0.2)

작성일: 2026-09-01 · 상태: 설계 확정 대기
변경: v0.2 — 보고 이력 관리 및 보고 대상 예측 설계 추가

---

## 1. 배경과 문제 정의

현재 팀의 과제별 수행 이력을 Obsidian 등 외부 클라우드 기반 마크다운 도구로 관리하고 있으나 다음 한계가 있다.

| 문제 | 영향 |
|---|---|
| 파일 첨부가 사실상 불가 | 실험 데이터(xlsx), 보고서 초안(docx/pptx), 참고 논문(PDF)을 별도 위치에 보관 → 이력과 자료가 분리됨 |
| 이미지 첨부/붙여넣기 불편 | 스크린샷 기반 기록(계측 화면, 그래프)이 누락되거나 외부 링크로 관리됨 |
| 과제 단위 관리 정보 부재 | 상태·마감일·분류를 문서 본문에 수기로 적어야 하고 목록에서 한눈에 안 보임 |
| 이력 취합 어려움 | 보고 시점에 과제 전체 이력을 하나로 묶어 내보내기 곤란 |
| 보고 이력이 남지 않음 | 매주 전체가 아니라 2–3개 과제만 보고하는데, **어느 과제를 언제 마지막으로 보고했는지** 추적되지 않아 보고 시점을 감으로 판단하게 됨 |
| 보고 당시 문서를 다시 못 봄 | 보고에 쓴 정리 문서(엑셀)가 이력과 분리 보관되어, 나중에 "그때 뭐라고 보고했는지" 확인이 어려움 |

**목표**: 마크다운의 가벼움과 이식성은 유지하면서, 첨부 파일·이미지를 이력과 같은 자리에 붙이고, 과제 단위로 진행 상황을 조회·검색·내보내기 할 수 있는 웹 기반 도구를 만든다.
아울러 **보고 이력과 보고 당시 문서를 과제에 함께 남겨**, 매주 어느 과제를 보고할지 근거를 가지고 고를 수 있게 한다.

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
| 보고 이력 | 과제별 **보고 이력**과 **보고 당시 문서**를 함께 보관. 현재는 **날짜만** 기록하고 유형·피보고자는 추후 확장 |
| 보고 자료 형태 | **엑셀(xlsx)** 로 보고. 본문은 텍스트, 필요 시 이미지 포함 |
| 보고 대상 선정 기준 | **마지막 보고 후 경과 기간** + **보고 이후 쌓인 새 진행 분량** |

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
5. **보고 스냅샷은 불변이다.**
   보고는 "그 시점에 무엇을 보고했는가"라는 사실 기록이므로, 확정된 보고 문서는 이후 진행일지가 바뀌어도 함께 바뀌지 않는다. 진행 이력(계속 자라는 것)과 보고 기록(그 시점에 고정되는 것)을 별도 폴더로 분리한 이유다.

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
│   │   ├── reports/                    # 보고 이력 (보고 시점에 고정된 스냅샷)
│   │   │   └── 2026-09-05/
│   │   │       ├── report.md           # 보고 당시 정리된 문서 (읽기 전용)
│   │   │       └── assets/
│   │   │           ├── 001-주간보고.xlsx    # 실제 보고에 사용한 원본 파일
│   │   │           └── 002-보고화면.png
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

### 4.4 보고 문서 (`reports/YYYY-MM-DD/report.md`)

보고 시점에 **고정(freeze)** 되는 스냅샷이다. 확정된 뒤에는 도구 UI에서 읽기 전용으로 열리며, 이후 진행일지를 수정해도 이 문서는 바뀌지 않는다. "그때 무엇을 어떻게 보고했는가"가 그대로 남는 것이 목적이다.

```markdown
---
report_date: 2026-09-05
title: 2026-09-05 보고
covers_from: 2026-08-22        # 이 보고가 포함한 진행일지 기간
covers_to: 2026-09-05
covered_entries:               # 이 보고에 반영된 진행일지 (미보고 분량 계산의 기준)
  - logs/2026-08-25-셀조립.md
  - logs/2026-09-03-1차측정결과.md
attachments:
  - assets/001-주간보고.xlsx
frozen_at: 2026-09-05T17:40:00+09:00
# 아래는 예약 필드 — 지금은 비워 두고 필요해질 때 UI에 노출
report_type:                   # weekly | monthly | ad_hoc | interim | final
audience:                      # 팀회의 / 부서장 / 고객사 …
---

## 보고 요약
- 셀 3종 조립 완료, 1차 수명 측정 착수
- 초기 용량 유지율 A안 98.2% / B안 95.7%

## 특이사항 및 이슈
...

## 다음 계획
...
```

* `report.md` 본문은 **마지막 보고 이후의 진행일지에서 자동 생성한 초안**을 사용자가 다듬은 결과다 (5.6).
* 실제 보고에 사용한 **엑셀 파일 원본**은 `reports/<날짜>/assets/`에 함께 보관되어 언제든 같은 화면에서 열린다.

### 4.5 SQLite 인덱스 스키마

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
  last_reported_at TEXT,                 -- 파생값: 최신 확정 보고일 (report에서 계산)
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
  report_id     INTEGER REFERENCES report(id) ON DELETE SET NULL,  -- 보고 자료 첨부
  rel_path      TEXT NOT NULL,           -- 'assets/2026-09-03/001-측정그래프.png'
  orig_name     TEXT NOT NULL,
  mime          TEXT,
  size_bytes    INTEGER,
  sha256        TEXT,                    -- 중복 감지용(저장 위치는 상대경로 유지)
  created_at    TEXT,
  UNIQUE(project_id, rel_path)
);

CREATE TABLE report (
  id            INTEGER PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  report_date   TEXT NOT NULL,           -- '2026-09-05' (지금은 이 값만 필수)
  title         TEXT,
  rel_path      TEXT NOT NULL,           -- 'reports/2026-09-05/report.md'
  covers_from   TEXT,
  covers_to     TEXT,
  body          TEXT,
  frozen_at     TEXT,                    -- NULL이면 아직 작성 중인 초안
  report_type   TEXT,                    -- 예약 필드 (추후 확장)
  audience      TEXT,                    -- 예약 필드 (추후 확장)
  file_mtime    REAL,
  UNIQUE(project_id, rel_path)
);

-- 어떤 진행일지가 어느 보고에 포함되었는지 → '미보고 분량' 계산의 근거
CREATE TABLE report_entry (
  report_id INTEGER REFERENCES report(id) ON DELETE CASCADE,
  entry_id  INTEGER REFERENCES entry(id)  ON DELETE CASCADE,
  PRIMARY KEY(report_id, entry_id)
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
| **과제 목록 / 보드** | 기본 진입 화면. 상태별 칸반 보드 ↔ 테이블 뷰 전환. 컬럼: 제목, 상태, 그룹, 태그, 마감일(D-day 배지), 최근 업데이트, **마지막 보고일 / 보고 후 경과일 / 미보고 진행 건수**. 필터: 상태·그룹·태그·기간, 정렬: 최근 업데이트순(기본)/마감일순/**보고 경과일순** |
| **과제 상세** | 상단에 개요(index.md) 렌더링 + 메타 편집 패널, 하단에 진행일지 타임라인(최신순). 각 일지는 접기/펼치기, 인라인 편집 진입. 타임라인에 **보고 시점 마커**가 함께 찍혀 "어디까지 보고했는지"가 한눈에 보임 |
| **보고 이력 (과제 상세 내 탭)** | 해당 과제의 보고를 날짜 역순으로 나열. 각 행에서 보고 당시 `report.md`(읽기 전용)와 보고에 사용한 엑셀 원본을 바로 열람 |
| **보고 대상 후보** | 전체 과제를 "마지막 보고 후 경과일 × 미보고 진행 분량" 기준으로 정렬한 대시보드. 매주 보고할 2–3개를 고르는 전용 화면 (5.7) |
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

병합 문서 말미에는 **보고 이력 요약**(보고일 목록 + 각 보고의 요약 첫 줄)을 덧붙이며, `?include=reports_full`을 주면 각 보고의 `report.md` 전문도 함께 포함한다.

추가로 `format=html`(단일 HTML, 이미지 인라인 — 보고용 공유에 편리), `format=zip`(원본 파일 구조 그대로 백업)을 제공한다.

### 5.5 외부 편집 동기화

* 앱 기동 시 vault 전체 스캔 → `file_mtime` 비교로 변경분만 재인덱싱.
* 실행 중에는 `watchdog`으로 vault 감시, 변경 파일만 증분 인덱싱(디바운스 500ms).
* `POST /api/reindex`로 전체 재구축 가능. DB를 지워도 데이터 손실이 없다.

### 5.6 보고 작성 흐름 (초안 자동 생성 → 정리 → 확정)

```
[과제 상세 → "보고 작성"]
        │
        ▼ 마지막 보고 이후의 진행일지를 자동 수집
POST /api/projects/{id}/reports/draft
        │
        ├─ 기간: 직전 보고의 covers_to 다음날 ~ 오늘
        ├─ 해당 구간 진행일지 본문·이미지를 모아 report.md 초안 생성
        └─ 상태: 초안 (frozen_at = NULL, 자유롭게 편집 가능)
        │
        ▼ 사용자가 편집기에서 보고용으로 다듬음
        │  · 요약 / 특이사항 / 다음 계획 3단 구성 기본 템플릿
        │  · 엑셀 붙여넣기용 복사 버튼 (아래 참조)
        │  · 실제 보고에 쓴 .xlsx 업로드
        ▼
POST /api/reports/{report_id}/freeze
        │
        ├─ report.md 읽기 전용 전환 (frozen_at 기록)
        ├─ 포함된 진행일지를 report_entry에 기록 → 이후 '미보고 분량'은 여기서부터 재계산
        └─ 과제의 last_reported_at 갱신
```

**엑셀 보고 지원** — 실제 보고는 엑셀로 하므로, 도구는 엑셀을 대체하지 않고 **엑셀로 옮기는 마지막 한 걸음을 줄이는 데** 집중한다.

| 기능 | 동작 |
|---|---|
| 엑셀 붙여넣기용 복사 | 보고 초안의 항목을 셀 단위로 바로 붙여넣을 수 있게 TSV/평문으로 클립보드 복사. 마크다운 기호(`-`, `**`)는 제거 |
| 보고 엑셀 원본 보관 | 보고에 사용한 `.xlsx`를 `reports/<날짜>/assets/`에 첨부. "그때 그 파일"이 이력에 붙어 있음 |
| 엑셀 내용 미리보기 | 업로드된 xlsx를 `openpyxl`로 읽어 첫 시트의 표와 삽입 이미지를 HTML로 렌더링. 서식은 재현하지 않으며 원본 다운로드를 항상 함께 제공 |
| 이미지 첨부 | 보고에 쓴 그래프·화면 캡처는 진행일지와 동일하게 붙여넣기 업로드 |

> 보고 유형(주간/월간/수시)과 피보고자는 스키마와 front matter에 **예약 필드로만 넣어 두고 UI에는 노출하지 않는다.** 필요해지는 시점에 입력란과 필터만 추가하면 되고, 그 전에 기록된 보고들도 그대로 유효하다.

### 5.7 보고 대상 예측

매주 전체 과제를 보고하는 것이 아니라 2–3건만 고르므로, **"지금 보고해야 할 과제"를 도구가 먼저 제시**한다. 근거는 두 가지다.

| 지표 | 정의 |
|---|---|
| `days_since_report` | 오늘 − 마지막 보고일 (보고 이력이 없으면 과제 시작일 기준) |
| `unreported_entries` | 마지막 보고 이후 작성된 진행일지 건수 (`report_entry`에 없는 일지) |

정렬 기본값은 두 지표를 함께 반영한 단순 점수이며, **점수와 함께 원본 수치를 항상 같이 표시**해 왜 위에 올라왔는지 바로 보이게 한다.

```
score = days_since_report / 기준주기(기본 7일)  +  unreported_entries × 0.5
```

* 기준주기·가중치는 설정값으로 두어 실제 보고 리듬에 맞게 조정한다.
* 상태가 `보류`·`완료`·`중단`인 과제는 후보에서 제외(토글로 포함 가능).
* 각 행에 "보고 경과 D+21 · 미보고 4건" 배지와 **[보고 초안 만들기]** 버튼을 두어, 후보 선정 → 초안 생성이 한 화면에서 이어진다.
* 과제 상세와 목록에도 같은 배지를 노출해 어디서든 보고 시점을 가늠할 수 있게 한다.

> 향후 확장 여지: 과제별 목표 보고 주기(예: 이 과제는 2주에 한 번)를 지정하면 `days_since_report`를 그 주기로 나눠 과제마다 다른 리듬을 반영할 수 있다. 지금은 전역 기준주기 하나로 시작한다.

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
| GET | `/api/projects/{id}/reports` | 보고 이력 목록(날짜 역순) |
| POST | `/api/projects/{id}/reports/draft` | 미보고 진행일지로 보고 초안 생성 |
| GET/PATCH | `/api/reports/{report_id}` | 보고 문서 조회/수정(확정 전에만 수정 가능) |
| POST | `/api/reports/{report_id}/freeze` | 보고 확정(스냅샷 고정) |
| POST | `/api/reports/{report_id}/unfreeze` | 확정 해제(오기입 정정용, 이력에 표시) |
| DELETE | `/api/reports/{report_id}` | 보고 삭제(`.trash/` 이동) |
| POST | `/api/reports/{report_id}/attachments` | 보고 자료(xlsx·이미지) 업로드 |
| GET | `/api/reports/{report_id}/export` | 보고 문서 단독 내보내기(md/HTML) |
| GET | `/api/report-candidates` | 보고 대상 후보 목록(경과일·미보고 건수·점수) |
| POST | `/api/entries/{entry_id}/attachments` | 첨부 업로드(multipart) |
| GET | `/api/attachments/{id}` | 원본 다운로드 |
| GET | `/api/attachments/{id}/thumb` | 이미지 썸네일 |
| GET | `/api/attachments/{id}/preview` | xlsx 표·이미지 추출 미리보기(HTML) |
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
| 엑셀 읽기 | `openpyxl` | 보고용 xlsx 표·삽입 이미지 미리보기 |
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
│   │   ├── api/                 # projects / entries / reports / attachments / search / export
│   │   └── services/            # attachments.py, export.py, thumbnails.py,
│   │                            # reports.py(초안 생성·확정), xlsx_preview.py
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
| **M4. 보고 이력 & 보고 예측** | 보고 초안 자동 생성 → 정리 → 확정(스냅샷), 보고 자료(xlsx) 첨부·미리보기, 보고 이력 탭, 보고 대상 후보 대시보드, 엑셀 붙여넣기용 복사 | 매주 "어느 과제를 보고할지"를 도구가 근거(경과일·미보고 건수)와 함께 제시하고, 과거 보고 문서를 그 자리에서 다시 열 수 있다 |
| **M5. 내보내기 & 백업** | 단일 md 병합(zip/inline/link), 보고 이력 포함, HTML, 전체 zip 백업 | 보고 직전 과제 이력을 md 한 개로 받아 그대로 붙여넣을 수 있다 |
| **M6. 서버 확장 (선택)** | Docker 이미지, 간단 인증, 다중 사용자 대비 잠금 | 사내 서버에 올려 팀원이 조회 가능 |

M1~M2까지가 첨부 관련 불편을 해소하는 최소 유용 제품(MVP)이고, **M4가 "보고 시점 예측"이라는 두 번째 핵심 가치**를 완성한다.

---

## 9. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| vault를 외부 도구로 동시 편집하며 덮어쓰기 | 저장 전 `file_mtime` 비교 → 변경 감지 시 사용자에게 알리고 덮어쓰기 여부 확인 |
| 첨부 누적으로 저장소 비대화 | 과제별 용량 표시, 업로드 상한(기본 50MB/건), 중복 파일 감지 |
| 백업 부재 | vault 폴더를 그대로 복사하면 완전 백업. 선택적으로 vault를 git 저장소로 두고 커밋 자동화 검토 |
| 한국어 전문 검색 품질 | trigram으로 시작, 부족하면 형태소 분석기 도입 |
| 확정된 보고 문서를 나중에 고치고 싶어짐 | 원칙은 읽기 전용이나 `unfreeze`로 해제 가능하게 하되, 해제·재확정 시각을 front matter에 남겨 사후 수정 여부가 드러나게 함 |
| 엑셀 미리보기가 원본 서식과 다름 | 표와 이미지 추출 수준으로만 제공하고 원본 다운로드를 항상 병행. 서식 재현이 목적이 아님을 UI에 명시 |
| 보고 없이 오래 방치된 과제의 경과일이 무한정 커짐 | 후보 점수 상한을 두고, 상태가 보류·완료·중단이면 후보에서 제외 |
| 경로 traversal / 파일명 충돌 | 모든 경로를 vault 루트 기준으로 정규화 후 검증, 파일명은 순번 접두사로 유일성 확보 |

---

## 10. 확정 필요 사항 (구현 착수 전)

1. **vault 기본 위치** — 예: `~/Documents/과제이력` (OneDrive/사내 동기화 폴더 안에 두면 자동 백업 효과)
2. **기존 Obsidian 문서 이관** — 지금 쓰는 노트를 가져올지, 새로 시작할지. 가져온다면 폴더 구조 샘플 필요
3. **첨부 용량 상한** — 기본 50MB로 제안. 실제 첨부하는 xlsx/PDF 크기에 맞춰 조정
4. **과제 상태 값** — `계획 / 진행중 / 보류 / 완료 / 중단` 5단계로 제안. 실제 업무 용어에 맞게 확정 필요
5. **과제 그룹 체계** — 그룹을 단일 값으로 둘지, 계층(대분류/중분류)으로 둘지
6. **보고 기준 주기** — 보고 후보 점수 계산의 기준값. 주간 정례라면 7일로 제안
7. **현재 사용 중인 보고 엑셀 양식 샘플** — 초안의 "엑셀 붙여넣기용 복사" 출력 형태(열 구성, 항목 순서)를 실제 양식에 맞추려면 파일 한 부가 필요
8. **과거 보고 이력 이관 여부** — 지금까지의 보고 기록·엑셀 파일을 초기 데이터로 넣을지 (넣는다면 날짜와 파일만으로 등록하는 간이 입력 화면을 M4에 포함)
