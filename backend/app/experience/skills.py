"""역량 사전 (TODO 260 · 253 의 4단계 — docs/팀원이력정리/4단계.md 2절).

기본 사전은 설계 원본 `docs/04_DATA_MODEL.md` 9절의 표 그대로다(원본 글은 "50개" 라 적었지만 표는 46개 — 표를 따른다).
**이름 맞추기**(원본 FR-C9) — 공백 · 가운뎃점 · 대소문자를 무시하고 대표 이름 또는 동의어와 같으면 대표 이름 · 사전의 축으로 바꾼다.
못 맞춘 이름은 그대로 둔다(4단계.md ② · ③ — 확정을 막지 않고 "사전에 없음" 으로 보일 뿐).
파일 · DB 를 모른다(1단계 모듈과 같은 결).
"""
from __future__ import annotations

import re
from typing import Any, Iterable

AXES = ("기술", "업무", "리더십", "문제해결")
NAME_MAX = 60
ALIAS_MAX = 20

# (축, 대표 이름, 동의어) — 원본 9절 v0.1
DEFAULT_SKILLS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ('기술', '비전 AI 객체탐지', ('객체탐지', 'CNN', '머신비전', '비전 AI')),
    ('기술', '시계열 분석·이상탐지', ('시계열', '이상탐지', '센서 데이터 분석')),
    ('기술', '자연어 처리', ('NLP', '텍스트 분석')),
    ('기술', '최적화·시뮬레이션', ('최적화', '시뮬레이터', '배합 최적화', '설비 운영 최적화')),
    ('기술', '예측 모델링', ('수요 예측', '재고 예측', '회귀')),
    ('기술', '데이터 파이프라인', ('ETL', '실시간 스트림', '데이터 수집')),
    ('기술', 'AI 인프라·플랫폼', ('GPU', 'HPC', 'MLOps', 'AI Lifecycle', '개발환경')),
    ('기술', '평가 지표 설계·검증', ('AUROC', '정밀도', '회귀 테스트', '벤치마크 환산')),
    ('기술', '실시간 시스템 개발', ('C#', '운영 시스템', '다계층 아키텍처')),
    ('기술', '생성형 AI 활용', ('AI 코딩 도구', '프롬프트', '프로토타이핑')),
    ('기술', 'CI/CD·배포', ('GitHub Actions', '파이프라인', '앱 배포')),
    ('기술', 'ERP·MES 연계', ('RFID', '실적 트래킹', '공정 이력')),
    ('기술', '프로세스 마이닝', ('병목 탐지', '공정 분석')),
    ('업무', '투자 심의·거버넌스 설계', ('심의 기준', 'Gate Review', '포트폴리오 거버넌스')),
    ('업무', '경영층 커뮤니케이션', ('경영층 보고', '투자 안건', '발표')),
    ('업무', '전략 기획·로드맵', ('중장기 전략', '로드맵 수립')),
    ('업무', '과제 포트폴리오 관리', ('포트폴리오 매니지먼트', '우선순위 선정')),
    ('업무', '교육 과정 설계', ('PBL', '러닝 패스', '커리큘럼')),
    ('업무', '프로세스 표준화', ('공통 프레임', '업무 표준')),
    ('업무', '요구사항 관리', ('요구사항 정의', '현업 합의')),
    ('업무', '제조 공정 이해', ('공정 지식', '도메인 이해')),
    ('업무', '품질 관리', ('품질 판정', '불량 관리')),
    ('업무', '그룹사·대외 협업', ('계열사 교류', '대외 발표', '산학 연계')),
    ('업무', '투자·예산 확보', ('예산', '투자 승인')),
    ('업무', '행사·프로그램 운영', ('페스티벌', '교류회', '세미나')),
    ('업무', '제품 기획', ('서비스 기획', '요구사항 정의')),
    ('리더십', '조직 설계·인력 배분', ('파트 편성', '배분 원칙')),
    ('리더십', '권한 위임', ('위임', '리스크 기준선')),
    ('리더십', '육성·온보딩', ('온보딩', '멘토링', '인재 육성')),
    ('리더십', '학습 문화 운영', ('공유 세션', '지식 축적')),
    ('리더십', '조직 간 조율', ('이해관계 조율', '조직 간 협업')),
    ('리더십', '운영 체제 전환', ('외주→내재화', '조달 방식 판단')),
    ('리더십', '조직 학습 설계', ('실패의 제도화', 'Learning Loop')),
    ('리더십', '면담·성장 설계', ('정기 면담', '개인 성장')),
    ('리더십', '변화 관리', ('전환 추진', '표준 정착')),
    ('리더십', '팀 운영', ('회의 운영', '팀 관리')),
    ('문제해결', '문제 재정의', ('문제 정의', '재구성')),
    ('문제해결', '목표 역산', ('사업 목표에서 성능 목표 도출',)),
    ('문제해결', '성과 지표 재정의', ('지표 설계', 'KPI 재설정')),
    ('문제해결', '지표의 함정 발견', ('평가 오류 발견', '검증 설계')),
    ('문제해결', '병목 진단', ('병목 분석',)),
    ('문제해결', '실패 원인 분석', ('사후 분석', '교훈 도출')),
    ('문제해결', '제약 우회', ('제약 극복', '대안 설계')),
    ('문제해결', '우선순위 기준 수립', ('선별 기준', '판단 기준')),
    ('문제해결', '가설 검증·파일럿', ('선검증', 'PoC')),
    ('문제해결', '도구 자체 구축', ('업무 도구 제작',)),
)


def default_dictionary() -> list[dict[str, Any]]:
    return [{"axis": axis, "name": name, "aliases": list(aliases)} for axis, name, aliases in DEFAULT_SKILLS]


def key(text: str) -> str:
    """맞추기 열쇠 — 공백 · 가운뎃점 · 쉼표 · 밑줄 · 하이픈을 지우고 소문자로."""
    return re.sub(r"[\s·・‧•_\-,]+", "", (text or "").strip()).lower()


def index(dictionary: Iterable[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """열쇠 → (축, 대표 이름). 대표 이름이 동의어보다 먼저, 같은 동의어가 둘이면 앞의 것(원본 표의 "요구사항 정의" 처럼)."""
    found: dict[str, tuple[str, str]] = {}
    items = list(dictionary)
    for item in items:
        found.setdefault(key(item["name"]), (item["axis"], item["name"]))
    for item in items:
        for alias in item.get("aliases") or []:
            found.setdefault(key(alias), (item["axis"], item["name"]))
    return found


def match(skills: Iterable[dict[str, str]], dictionary: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """역량 태그를 사전에 맞춘다 — 맞으면 대표 이름 · 사전의 축, 아니면 그대로. 같은 것은 하나로."""
    table = index(dictionary)
    out: list[dict[str, str]] = []
    for skill in skills:
        axis, name = table.get(key(skill.get("name", "")), (skill.get("axis", "기술"), skill.get("name", "")))
        if name and not any(s["axis"] == axis and s["name"] == name for s in out):
            out.append({"axis": axis, "name": name})
    return out


def unknown(skills: Iterable[dict[str, str]], dictionary: Iterable[dict[str, Any]]) -> list[str]:
    """사전에 없는 태그 이름 — 화면의 "사전에 없음"."""
    names = {(item["axis"], item["name"]) for item in dictionary}
    return [s["name"] for s in skills if (s.get("axis"), s.get("name")) not in names]


def validate(value: Any) -> list[dict[str, Any]] | None:
    """설정 `skill_dictionary` 의 모양 — None 이면 기본. 축 넷 · 이름 60자 · 같은 대표 이름 없음 · 동의어 20개까지."""
    if value is None or value == []:     # 빈 목록은 "기본 사전으로"(설정의 다른 목록 값과 같다)
        return None
    if not isinstance(value, list):
        raise ValueError("역량 사전은 목록이어야 합니다.")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("역량 사전의 항목 모양이 다릅니다.")
        axis = str(raw.get("axis") or "").strip()
        name = " ".join(str(raw.get("name") or "").split())
        if axis not in AXES:
            raise ValueError(f"역량 축은 {' · '.join(AXES)} 중 하나입니다: {axis or '(빈칸)'}")
        if not name or len(name) > NAME_MAX:
            raise ValueError(f"역량 이름은 1 ~ {NAME_MAX}자입니다: {name[:20] or '(빈칸)'}")
        if key(name) in seen:
            raise ValueError(f"같은 역량이 두 번 있습니다: {name}")
        seen.add(key(name))
        aliases_raw = raw.get("aliases") or []
        if isinstance(aliases_raw, str):
            aliases_raw = aliases_raw.split(",")
        aliases = list(dict.fromkeys(a for a in (" ".join(str(x).split()) for x in aliases_raw) if a and key(a) != key(name)))
        if len(aliases) > ALIAS_MAX or any(len(a) > NAME_MAX for a in aliases):
            raise ValueError(f"동의어는 {ALIAS_MAX}개 · 각 {NAME_MAX}자까지입니다: {name}")
        out.append({"axis": axis, "name": name, "aliases": aliases})
    return out
