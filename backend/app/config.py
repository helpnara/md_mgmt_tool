"""전역 설정. 상태 목록처럼 자주 바뀔 값은 모두 여기 모아 둔다."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# (키, 화면 라벨, 보고 후보에 기본 포함할지)
STATUSES: list[tuple[str, str, bool]] = [
    ("plan_report", "기획보고", True),
    ("proposal", "제안", True),
    ("review", "검토", True),
    ("in_progress", "진행중", True),
    ("on_hold", "보류", False),
    ("done", "완료", False),
    ("dropped", "중단", False),
]
STATUS_KEYS: list[str] = [key for key, _, _ in STATUSES]
STATUS_LABELS: dict[str, str] = {key: label for key, label, _ in STATUSES}
DEFAULT_STATUS = "in_progress"
# 보드에서 기본 접어 두는 상태
COLLAPSED_STATUSES = {"done", "dropped"}


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
