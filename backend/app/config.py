"""전역 설정. 상태 목록처럼 자주 바뀔 값은 모두 여기 모아 둔다."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 진행 상태 — 오직 '얼마나 진행됐는가'만 담는다.
# (키, 화면 라벨, 보고 후보에 기본 포함할지)
STATUSES: list[tuple[str, str, bool]] = [
    ("planned", "예정", True),
    ("reviewing", "검토중", True),
    ("in_progress", "진행중", True),
    ("on_hold", "보류", False),
    ("done", "완료", False),
    ("dropped", "중단", False),
]
STATUS_KEYS: list[str] = [key for key, _, _ in STATUSES]
STATUS_LABELS: dict[str, str] = {key: label for key, label, _ in STATUSES}
DEFAULT_STATUS = "in_progress"

# 과제 효과 금액의 단위. 사내에서 쓰는 표기를 그대로 따른다.
# 값은 이 단위의 숫자로만 저장하고(예: 1.2), 화면에서 단위를 붙여 보여 준다.
EFFECT_UNIT = "억원/년"
# 기대효과(착수 시 예상) / 실증효과(끝난 뒤 확인). 둘은 반드시 나눠 둔다 —
# 한 칸에 담으면 "예상은 얼마였고 실제로 얼마였나"를 되짚을 수 없다.
EFFECT_FIELDS = ("effect_expected", "effect_verified")

# 진행일지 기본 서식. 설정에서 속성별로 바꿀 수 있다 (services/settings.py).
# 빈칸에서 시작하면 무엇을 적을지부터 고민하게 되므로 뼈대를 준다.
DEFAULT_ENTRY_TEMPLATE = """## 내용

## 진행

## 계획
"""
# 보드에서 기본 접어 두는 상태
COLLAPSED_STATUSES = {"done", "dropped"}
# 끝난 과제 — 마감이 지났다고 경고하지 않는다.
# (보류는 멈춰 있을 뿐 끝난 것이 아니라서 그대로 경고한다. util.ts 의 FINISHED_STATUSES 와 같은 뜻)
FINISHED_STATUSES: tuple[str, ...] = ("done", "dropped")

# 과제 속성 — 과제의 '성격'. 상태와 달리 시간이 지나도 잘 바뀌지 않는다.
# 과제당 하나만 지정한다.
PROJECT_TYPES: list[tuple[str, str]] = [
    ("smart", "스마트과제"),
    ("rnd", "R&D"),
    ("investment", "투자"),
    ("plan_report", "기획보고"),
    ("national", "국책과제"),
    # 이미 돌아가는 것을 고쳐 가며 유지하는 일. 시작과 끝이 뚜렷한 위 넷과 성격이 다르지만
    # 팀이 실제로 시간을 쓰는 축이라 과제로 세운다 (TODO 99).
    ("maintenance", "유지보수"),
]
TYPE_KEYS: list[str] = [key for key, _ in PROJECT_TYPES]

# 과제 분류 넷 (TODO 136). **속성과 다른 축**이다 — 속성은 과제의 종류(스마트과제·기획보고…)이고,
# 이 넷은 주로 스마트과제 안에서 거르고 세는 축이다: 성격 · 기술 분류 · 수행 방식 · 효과의 비용 구분.
# 값은 **글자 그대로** 파일에 적는다(키를 따로 두지 않는다). 목록은 설정에서 고치고,
# 목록에서 빠진 값도 파일에서 지우지 않는다 — 명부에 없는 담당자 이름을 지우지 않는 것과 같다.
CLASSIFICATIONS: list[tuple[str, str, list[str]]] = [
    ("nature", "성격", ["연구과제/PoC", "현장적용", "확대전개", "기타"]),
    ("category", "분류", ["스마트 센싱", "원인분석/이상탐지", "예측/분류모델 개발", "가이던스/제어", "기타"]),
    ("delivery", "수행 방식", ["현업 자체 개발", "전문부서 개발", "외부 전문업체 협업"]),
    # KPI 가 여럿이면 고정비·변동비가 섞일 수 있다. 과제 칸은 대표값 하나다 — 그래서 '혼합'.
    ("cost_kind", "비용구분", ["고정비", "변동비", "혼합"]),
]
CLASSIFICATION_KEYS: list[str] = [key for key, _, _ in CLASSIFICATIONS]
CLASSIFICATION_LABELS: dict[str, str] = {key: label for key, label, _ in CLASSIFICATIONS}
# 이 칸들을 입력 화면에 세우는 속성. 다른 속성에는 의미가 없어 칸만 늘어난다.
CLASSIFIED_TYPE = "smart"

# 접수 상태 (TODO 136). 세 번째 값은 **풀에 담겨 있는가** — 아직 판정이 안 났거나 보류된 것.
# 풀은 상태가 아니라 화면이다. `pooled` 같은 상태를 따로 두면 "검토중" 과 겹쳐 둘 다 흐려진다.
INTAKE_STATUSES: list[tuple[str, str, bool]] = [
    ("received", "접수", True),
    ("reviewing", "검토중", True),
    ("on_hold", "보류", True),
    ("started", "착수", False),
    ("rejected", "반려", False),
    ("transferred", "이관", False),
    ("merged", "병합", False),
]
INTAKE_STATUS_KEYS: list[str] = [key for key, _, _ in INTAKE_STATUSES]
INTAKE_STATUS_LABELS: dict[str, str] = {key: label for key, label, _ in INTAKE_STATUSES}
INTAKE_POOL_STATUSES: tuple[str, ...] = tuple(key for key, _, pool in INTAKE_STATUSES if pool)
# 판정 — 풀에서 나가는 길. 착수는 승격으로만 간다(과제가 함께 생긴다).
INTAKE_DECISIONS: tuple[str, ...] = ("rejected", "transferred", "merged", "on_hold")
INTAKE_PRIORITIES: list[str] = ["상", "중", "하"]

# 팀원 역량 이력의 구분 (TODO 72). 과제의 '속성'과 다른 축이다.
# 기록 단위는 **사람**이다 — 한 행사에 세 명이 가면 기록도 세 건이다.
ACTIVITY_KINDS: list[tuple[str, str]] = [
    ("education", "교육"),
    ("seminar", "세미나"),
    ("expo", "박람회"),
    ("conference", "학회"),
    ("certificate", "자격·인증"),
    ("other", "기타"),
]
ACTIVITY_KIND_KEYS: list[str] = [key for key, _ in ACTIVITY_KINDS]
ACTIVITY_KIND_LABELS: dict[str, str] = dict(ACTIVITY_KINDS)
DEFAULT_ACTIVITY_KIND = "education"
TYPE_LABELS: dict[str, str] = {key: label for key, label in PROJECT_TYPES}

# 예전 값 → 새 값. 상태로 잘못 들어가 있던 '성격'은 속성으로 옮긴다.
# (기획보고 상태의 과제는 영영 '완료'가 될 수 없었다)
LEGACY_STATUS_MAP: dict[str, tuple[str, str | None]] = {
    "plan_report": ("planned", "plan_report"),   # 기획보고: 상태는 예정, 속성은 기획보고
    "proposal": ("planned", None),               # 제안: 아직 시작 전
    "review": ("reviewing", None),               # 검토: 검토중
}


def normalize_status(value: str | None) -> tuple[str, str | None]:
    """상태 값을 새 체계로 맞춘다. (상태, 함께 채울 속성) 을 돌려준다."""
    if not value:
        return DEFAULT_STATUS, None
    if value in STATUS_KEYS:
        return value, None
    if value in LEGACY_STATUS_MAP:
        return LEGACY_STATUS_MAP[value]
    return DEFAULT_STATUS, None


@dataclass(frozen=True)
class Settings:
    vault_dir: Path
    report_cycle_days: int = 7  # 보고 후보 점수의 기준 주기
    version_keep_days: int = 365  # 이전 버전 보관 기간 (2026-09-02 사용자 확정)

    @property
    def projects_dir(self) -> Path:
        return self.vault_dir / "projects"

    @property
    def people_dir(self) -> Path:
        """팀원 역량 이력. 과제가 아니므로 projects 밑에 두지 않는다 (TODO 72)."""
        return self.vault_dir / "people"

    @property
    def intakes_dir(self) -> Path:
        """접수 풀 (TODO 136). 요청 하나가 폴더 하나 — 과제와 같은 짜임이다."""
        return self.vault_dir / "intakes"

    @property
    def trash_dir(self) -> Path:
        return self.vault_dir / ".trash"

    @property
    def index_dir(self) -> Path:
        return self.vault_dir / ".index"

    @property
    def versions_dir(self) -> Path:
        """이전 버전 보관. vault 안에 두어 vault 를 옮기면 안전망도 함께 간다."""
        return self.vault_dir / ".versions"

    @property
    def logs_dir(self) -> Path:
        """오류 기록. vault 안에 두어 vault 를 옮기면 기록도 함께 간다."""
        return self.vault_dir / ".logs"

    @property
    def drafts_dir(self) -> Path:
        """쓰다 만 글 (TODO 170). 브라우저가 아니라 **이 PC 의 데이터 폴더**에 둔다 — 창 · 프로필 · 주소가
        달라도 같은 글이 돌아온다. 밖으로 나가는 것은 없다."""
        return self.vault_dir / ".drafts"

    @property
    def db_path(self) -> Path:
        return self.index_dir / "index.sqlite3"

    def ensure_dirs(self) -> None:
        for path in (self.vault_dir, self.projects_dir, self.people_dir, self.intakes_dir,
                     self.trash_dir, self.index_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    vault = os.environ.get("MD_MGMT_VAULT")
    vault_dir = Path(vault).expanduser().resolve() if vault else REPO_ROOT / "vault"
    return Settings(vault_dir=vault_dir)
