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
DEFAULT_ENTRY_TEMPLATE = """## 진행 내용

## 결과 · 확인한 것

## 다음 할 일
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
]
TYPE_KEYS: list[str] = [key for key, _ in PROJECT_TYPES]
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

    @property
    def projects_dir(self) -> Path:
        return self.vault_dir / "projects"

    @property
    def trash_dir(self) -> Path:
        return self.vault_dir / ".trash"

    @property
    def index_dir(self) -> Path:
        return self.vault_dir / ".index"

    @property
    def db_path(self) -> Path:
        return self.index_dir / "index.sqlite3"

    def ensure_dirs(self) -> None:
        for path in (self.vault_dir, self.projects_dir, self.trash_dir, self.index_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    vault = os.environ.get("MD_MGMT_VAULT")
    vault_dir = Path(vault).expanduser().resolve() if vault else REPO_ROOT / "vault"
    return Settings(vault_dir=vault_dir)
