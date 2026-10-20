from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# 시험의 '오늘' 을 고정한다 (TODO 219) — 시험은 2026년 날짜를 글자 그대로 쓴다. 실제 오늘을 읽으면 보고 날짜
# ±365일 같은 규칙에 밀려 2027년 가을쯤부터 멀쩡한 시험이 깨진다. 시험 안에서 오늘이 필요하면 `clock.today()`.
# 모듈을 읽을 때 정하는 값(`TODAY = clock.today()`)도 같은 날이 되도록 여기서, 맨 먼저.
FIXED_TODAY = "2026-10-20"
os.environ["MD_MGMT_TODAY"] = FIXED_TODAY


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MD_MGMT_VAULT", str(tmp_path / "vault"))
    from app.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()


@pytest.fixture()
def vault_dir(client):
    from app.config import get_settings

    return get_settings().vault_dir


@pytest.fixture()
def db(client):
    """서버가 쓰고 있는 그 커넥션. 서비스 함수를 직접 부르는 시험에 쓴다."""
    from app import deps

    return deps._conn
