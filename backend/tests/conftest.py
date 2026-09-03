from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


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
