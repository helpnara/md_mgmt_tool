# 문서 지도

이 폴더에 무엇이 있고, **무엇을 고치면 어느 문서를 함께 고치는지** 적어 둔다.
문서가 열 편을 넘으면서 "어디를 고쳐야 하지"가 매번 생각할 일이 됐기 때문이다 (TODO 133).

---

## 1. 살아 있는 문서 — 바뀌면 그날 고친다

| 문서 | 무엇 | 언제 고치나 |
|---|---|---|
| [TODO.md](TODO.md) | 접수한 요청과 **반영 결과** | 요청을 받을 때(접수) · 만든 날(결과). 이 도구의 이력 장부다 |
| [DESIGN.md](DESIGN.md) | 무엇을 왜 그렇게 정했는가 | **데이터 구조**(4절) · **화면·규칙**(5절) · **API**(6절) · **단계**(7절)가 바뀔 때 |
| [로드맵-확산단계.md](로드맵-확산단계.md) | 쓰는 사람이 늘어나는 순서 (1인 → 각자 배포 → 여러 팀장 → 팀원) | 단계가 바뀌거나, **남에게 건네는 방법**이 바뀔 때 |
| [ROADMAP.md](ROADMAP.md) | 기능 축 (R1·R2·R3) | 로드맵 항목의 상태가 바뀔 때 |
| [향후계획-브레인스토밍.md](향후계획-브레인스토밍.md) | 고르기 위한 후보 목록 (T1~T52) | 후보를 채택·제외할 때 |
| [사내AI-사용용도-검증안.md](사내AI-사용용도-검증안.md) | 사내 생성형 AI **사용 용도 검증** 제출 초안 | 제출 전까지 살아 있다. 검증 결과가 나오면 실측치로 갱신하고, 제출한 뒤에는 굳힌다 |
| [LESSONS-LEARNED.md](LESSONS-LEARNED.md) | 반복된 실수와 다음 웹 첫날 점검표 | **새로운 모양의 실수**를 겪었을 때만. 같은 모양이면 사례만 덧붙인다 |
| [../README.md](../README.md) | 설치·업데이트·사용 안내 | 설치 절차·배포본 이름·화면 이름이 바뀔 때 |
| [promo/](promo/) — 홍보 모션그래픽 | 블로그 · SNS 용 기능 소개 영상(58초 · 16:9 · 소리 없음)과 표지. `promo.html` 이 원본, `render.mjs` 가 mp4 로 | 기능을 더 알리고 싶을 때 `promo.html` 의 장면을 고치고 다시 만든다. **화면 속 자료는 지어낸 것만** — 실제 화면 · 이름 · 사내 분류를 넣지 않는다 |

## 2. 굳은 문서 — 그때의 사실이라 고치지 않는다

| 문서 | 왜 굳었나 |
|---|---|
| [성과공유회-발표초안.md](성과공유회-발표초안.md) · [poster/](poster/) | 🔒 **AX 성과공유회에 제출 완료** (2026-09-27 확정). 제출본이 최종이라 그 뒤 바뀐 이름·화면은 반영하지 않는다 |
| [검토-1인팀장-2026-09-09.md](검토-1인팀장-2026-09-09.md) | 그날의 **검토 기록**. 지금 상태로 고쳐 쓰면 "무엇을 왜 제안했나"가 사라진다. 달라진 것은 각주로만 붙인다 |
| [blog/느린나이테-블로그-초안.md](blog/느린나이테-블로그-초안.md) · 이미지 다섯 장 | 🔒 **네이버 블로그에 게시 완료** (2026-10-10). 게시한 글이 최종본이라 그 뒤 바뀐 도구는 반영하지 않는다. 숫자는 10-04 기준 |
| [외주개발-비용산정.md](외주개발-비용산정.md) | **2026-09-07 기준 고정.** 기능점수를 다시 산정하지 않는 한 금액만 갱신할 수 없다 |

> 굳은 문서에도 **각주는 붙인다** — "그 뒤 무엇이 달라졌는지" 한 줄. 본문은 건드리지 않는다.

---

## 3. 무엇을 바꾸면 어디를 고치나

| 바꾼 것 | 함께 고칠 곳 |
|---|---|
| 화면·기능 | TODO(결과) → DESIGN 5절 (필요하면 5.x 규칙) |
| 저장하는 값·파일 서식 | DESIGN **4절** (4.2 개요 · 4.3 진행일지 · 4.4 보고 · 4.8 설정 · 4.9 역량 · 4.10 접수 · 사전점검 스냅샷) + 스키마 버전 |
| 빌드를 사용자에게 건넬 때 | 번호 붙은 **체크리스트**를 함께 주고, 결과는 TODO 끝의 *체크리스트 — 확인 현황* 표에 쌓는다 (2026-09-29 부터) |
| API 끝점 | DESIGN **6절** 표와 **머리말의 개수** |
| 설치·배포본·업데이트 절차 | ../README.md + 확산 로드맵 2절 |
| 로드맵 항목의 상태 | ROADMAP + 확산 로드맵 (둘이 어긋나면 **확산 로드맵이 맞다** — 사람이 먼저다) |
| 이름·표시 같은 정체성 | ../README.md · DESIGN 머리말 · 확산 로드맵 1단계 표 |

**지난 기록은 고쳐 쓰지 않는다** (TODO 132). 이름이 바뀌어도 TODO 의 지난 항목은 그때 사실
그대로 두고 "어디서 바뀌었다" 한 줄만 붙인다. 이력 도구의 이력을 덮어쓰면 안 된다.

---

## 4. 반년에 한 번 — 읽지 말고 돌린다

문서는 **수를 적은 자리부터 낡는다.** 2026-09-27 점검에서 어긋난 열네 곳 중 아홉이
수·날짜·범위였다 (끝점 64개, 화면 시험 87건, TODO 1~127, 09-15 기준…).
그래서 눈으로 읽지 말고 아래를 돌린 뒤 **문서에 적힌 수와 다른 것만** 본다.

```bash
grep -rhoE '@router\.(get|post|put|patch|delete)\("' backend/app/api | wc -l   # 끝점 수 → DESIGN 6절 머리말
.venv/bin/python -m pytest backend/tests -q --collect-only | tail -1          # 백엔드 시험 수
node tests/ui/screens.mjs | tail -1                                           # 화면 시험 수
find docs -name '*.md' | xargs wc -l | tail -1                                # 문서 줄 수
git log --oneline | wc -l                                                     # 커밋 수
grep -n "SCHEMA_VERSION = " backend/app/db.py                                 # 스키마 버전 → DESIGN 4.7
```

설정 열쇠와 끝점이 문서에 다 있는지는 이렇게 본다 — 하나라도 빠지면 이름이 찍힌다.

```bash
python3 - <<'EOF'
import pathlib, sys
sys.path.insert(0, "backend")
from app.services.settings import DEFAULTS          # 설정 열쇠의 원본
doc = pathlib.Path("docs/DESIGN.md").read_text(encoding="utf-8")
print("문서(4.8)에 없는 설정 열쇠:", sorted(k for k in DEFAULTS if k not in doc))

import re
eps = set()
for f in pathlib.Path("backend/app/api").glob("*.py"):
    src = f.read_text(encoding="utf-8")
    m = re.search(r'APIRouter\(prefix="([^"]*)"', src)
    pre = m.group(1) if m else ""
    for meth, path in re.findall(r'@router\.(get|post|put|patch|delete)\("([^"]*)"', src):
        eps.add(re.sub(r"\{[^}]*\}", "{}", pre + path).rstrip("/"))
shown = {re.sub(r"\{[^}]*\}", "{}", p).rstrip("/") for p in re.findall(r'`(/(?:api|files|intake-files)[^`]*)`', doc)}
print("문서(6절)에 없는 끝점:", sorted(e for e in eps if e not in shown))
EOF
```

> 끝점 검사는 표기가 달라도(`{id}` / `{project_id}`) 같게 보도록 이름을 지우고 견준다.
> 남는 몇 개는 `/api/versions` · `/unfreeze` · 접수의 `logs[/{name}]` 처럼 **한 줄에 묶어 적은 것**이라 눈으로 확인한다.
