"""Black-box probe harness. Run from backend dir with the venv python."""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path("/home/user/md_mgmt_tool/backend")
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

SCRATCH = Path("/tmp/claude-0/-home-user-md-mgmt-tool/c32970f6-4741-525a-bf74-43fa93408437/scratchpad/probe")
RESULTS: list[dict] = []
_COUNTS = {"ok": 0, "PROBLEM": 0, "note": 0}


def rec(name: str, request: str, resp, verdict: str, why: str = "", sev: str = "") -> None:
    """verdict: ok | PROBLEM | note"""
    status = resp.status_code if hasattr(resp, "status_code") else resp
    body = ""
    if hasattr(resp, "text"):
        body = resp.text[:300].replace("\n", " ")
    row = {"name": name, "request": request, "status": status, "verdict": verdict, "why": why, "sev": sev, "body": body}
    RESULTS.append(row)
    _COUNTS[verdict] = _COUNTS.get(verdict, 0) + 1
    mark = {"ok": " ", "PROBLEM": "!", "note": "?"}.get(verdict, " ")
    print(f"[{mark}] {status} {name} :: {request} :: {why} :: {body[:160]}")


def finish(tag: str) -> None:
    out = SCRATCH / f"results_{tag}.json"
    out.write_text(json.dumps({"counts": _COUNTS, "rows": RESULTS}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"== {tag}: {_COUNTS}  -> {out}")


@contextlib.contextmanager
def fresh(share: bool = False, client_addr: tuple[str, int] | None = None, keep: bool = False):
    """Fresh temp vault + TestClient (pattern from tests/conftest.py)."""
    tmp = Path(tempfile.mkdtemp(prefix="probe_vault_", dir=str(SCRATCH)))
    vault = tmp / "vault"
    os.environ["MD_MGMT_VAULT"] = str(vault)
    if share:
        os.environ["MD_MGMT_SHARE"] = "1"
    else:
        os.environ.pop("MD_MGMT_SHARE", None)
    from app.config import get_settings
    get_settings.cache_clear()
    from app import share as share_mod
    share_mod._today = {"date": None, "ips": set(), "requests": 0}
    from fastapi.testclient import TestClient
    from app.main import app
    kwargs = {}
    if client_addr:
        kwargs["client"] = client_addr
    try:
        with TestClient(app, **kwargs) as c:
            yield c, vault
    finally:
        get_settings.cache_clear()
        os.environ.pop("MD_MGMT_SHARE", None)
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


def tree(root: Path, limit: int = 200) -> list[str]:
    out = []
    for p in sorted(root.rglob("*")):
        if ".index" in p.parts:
            continue
        out.append(str(p.relative_to(root)) + ("/" if p.is_dir() else f" ({p.stat().st_size}b)"))
        if len(out) >= limit:
            out.append("...")
            break
    return out


def project_dirs(vault: Path) -> list[str]:
    d = vault / "projects"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def is_korean(msg: str) -> bool:
    return any("가" <= ch <= "힣" for ch in msg)


def detail(resp) -> str:
    try:
        d = resp.json().get("detail")
    except Exception:
        return resp.text[:200]
    return d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)[:300]
