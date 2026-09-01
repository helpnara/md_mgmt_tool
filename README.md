# 과제 이력 관리 도구

과제별 수행 이력을 마크다운으로 관리하는 웹 기반 도구.
파일·이미지 첨부를 이력과 같은 자리에 보관하고, 과제 단위로 진행 상황을 조회·검색·내보내기 한다.

- 데이터는 일반 `.md` 파일과 폴더로 저장된다 (Obsidian·VS Code 등에서 그대로 열림)
- 첨부는 과제 폴더 내 `assets/`에 상대경로로 저장 → 어떤 뷰어에서도 이미지가 보임
- SQLite는 검색·필터용 파생 인덱스이며 언제든 재생성 가능

---

## 윈도우에서 시작하기

Python 3.10 이상이 필요하다. ([python.org](https://www.python.org/downloads/) — 설치 화면에서
**“Add python.exe to PATH”** 를 반드시 체크할 것)

1. 이 저장소를 받아 압축을 푼다.
2. **`setup.bat`** 을 더블클릭한다 → 가상환경(`.venv`)을 만들고 필요한 패키지를 설치한다.
3. **`run.bat`** 을 더블클릭한다 → 브라우저가 열리고 도구가 뜬다.

두 번째 실행부터는 `run.bat` 만 누르면 된다. 종료는 검은 창에서 `Ctrl+C`.

```
run.bat                     기본 실행 (http://127.0.0.1:8000)
run.bat --port 9000         포트 변경
run.bat --vault D:\과제이력  데이터 폴더 위치 지정
```

> 화면 UI(`frontend/dist`)는 미리 빌드해 저장소에 포함해 두었으므로 **Node.js는 필요 없다.**
> UI 코드를 고칠 때만 `frontend`에서 `npm install && npm run build`가 필요하다.

### macOS / 리눅스

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
python3 run.py          # 또는 ./run.sh
```

---

## 데이터가 저장되는 모습

기본 위치는 이 폴더 아래 `vault/` 이며 `--vault` 로 바꿀 수 있다.

```
vault/projects/2026-001-리튬전지-장수명-셀-설계/
├── index.md                        과제 개요 + 메타데이터(front matter)
├── logs/
│   └── 2026-09-03-1차-수명-측정-결과.md
├── assets/
│   └── 2026-09-03/
│       ├── 001-측정그래프.png
│       └── 002-원시데이터.xlsx
└── reports/                        보고 이력 (M4에서 사용)
```

`vault/` 폴더만 복사하면 그대로 백업이며, `.index/`(SQLite)는 지워도 실행 시 다시 만들어진다.
폴더를 직접 수정했다면 화면 우측 상단의 **[다시 읽기]** 를 누르면 반영된다.

---

## 지금까지 구현된 것

| 단계 | 내용 | 상태 |
|---|---|---|
| M0 | 실행 스크립트, vault 초기화, SQLite 스키마 | 완료 |
| M1 | 과제·진행일지 작성/수정, 파일 기반 저장, 재인덱싱 | 완료 |
| M2 | 이미지 붙여넣기·파일 첨부(진행률 표시), 자동 저장 토글 | 완료 |
| M3 | 상태 보드, 마감 필터, 통합 검색 | 완료 |
| M4 | 보고 이력·보고 대상 예측 | 예정 |
| M5 | 단일 md 내보내기, 백업 | 예정 |

## 문서

- [설계 문서](docs/DESIGN.md)

## 개발

```bash
.venv/bin/python -m pytest backend/tests -q     # 백엔드 테스트
cd frontend && npm run dev                      # UI 개발 서버 (API는 8000번으로 프록시)
```
