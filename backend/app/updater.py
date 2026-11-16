"""zip 을 업데이트 폴더에 두면 업데이트 (TODO 298) — 표준 라이브러리만 쓴다(`run.py` 가 앱을 읽기 **전에** 부른다).

사용자(2026-11-17): *"zip 파일만 사내 특정 폴더에 두면 자동으로 업데이트 되게 가능한지"* → 권하는 대로:
* 업데이트 폴더 — 기본 `<설치 폴더>/updates`, 설정 `update_dir` 로 사내 공유 폴더.
* 서버 PC 화면에 새 판 알림 → 관리자가 [이 판으로 업데이트] → (앱) 데이터 백업 · `updates/pending.json` 적기 · 스스로 끝남(코드 3)
  → `run.bat` 이 다시 켬 → `run.py` 가 **앱을 읽기 전에** `apply_pending()` 으로 적용하고 새 `run.py` 로 다시 시작.
* 지키는 것 — `vault` · `demo-vault` · `data-mode.json` · `.venv` · `updates` 는 건드리지 않는다. 바뀌는 프로그램 파일은
  `updates/되돌리기/<옛 판>/` 에 보관 → `run.bat --rollback` 으로 되돌린다.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

TOP = "느린나이테"
INFO = "배포본-정보.txt"
MANIFEST = "배포본-파일목록.txt"
PENDING = "pending.json"
STATE = "update-state.json"
APPLIED_DIR = "적용됨"
ROLLBACK_DIR = "되돌리기"
WORK_DIR = ".work"
# 업데이트가 건드리지 않는 것(설치 폴더 맨 위 이름) — 데이터 · 모드 · 파이썬 환경 · 업데이트 폴더
PROTECTED = {"vault", "demo-vault", "data-mode.json", ".venv", "venv", "updates", ".git", "node_modules"}
NAME_RE = re.compile(r"^느린나이테-(\d{8})-v(\d+)")


class UpdateError(RuntimeError):
    pass


# ── 판 이름 ─────────────────────────────────────────────────────────────────────────────────────────

def version_key(name: str) -> tuple[int, int] | None:
    """`느린나이테-20261116-v6(-no-vendor)` → (20261116, 6). 아니면 None."""
    found = NAME_RE.match(name)
    return (int(found.group(1)), int(found.group(2))) if found else None


def current_version(root: Path) -> str:
    """설치 폴더의 `배포본-정보.txt` 의 "배포본 이름". 개발 폴더(없음)는 ""."""
    try:
        for line in (root / INFO).read_text(encoding="utf-8").splitlines():
            if line.startswith("배포본 이름"):
                return line.split(None, 2)[-1].strip() if len(line.split(None, 2)) == 3 else ""
    except OSError:
        pass
    return ""


def update_dir(root: Path, configured: str = "") -> Path:
    folder = (configured or "").strip()
    return Path(folder).expanduser() if folder else root / "updates"


# ── 찾기 · 검사 ─────────────────────────────────────────────────────────────────────────────────────

def _sha_file(zip_path: Path) -> Path:
    return zip_path.with_name(zip_path.name + ".sha256")


def verify(zip_path: Path) -> str:
    """배포본 zip 이 맞으면 "" — 아니면 까닭. 검사값(.sha256)이 있으면 맞춰 본다(없으면 넘어간다)."""
    if not zip_path.is_file():
        return "파일이 없습니다."
    sha = _sha_file(zip_path)
    if sha.is_file():
        want = sha.read_text(encoding="utf-8").split()[0].strip().lower() if sha.read_text(encoding="utf-8").strip() else ""
        digest = hashlib.sha256()
        with zip_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        if want and digest.hexdigest() != want:
            return "검사값(.sha256)이 맞지 않습니다 — 내려받다 깨졌거나 바뀐 파일입니다."
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            bad = archive.testzip()
    except (zipfile.BadZipFile, OSError) as exc:
        return f"zip 을 열 수 없습니다 ({exc})."
    if bad:
        return f"zip 안의 파일이 깨졌습니다: {bad}"
    for need in ("run.py", INFO, "backend/app/main.py"):
        if f"{TOP}/{need}" not in names:
            return f"느린 나이테 배포본이 아닙니다 — {TOP}/{need} 가 없습니다."
    for name in names:
        parts = PurePosixPath(name).parts
        if not parts or parts[0] != TOP or ".." in parts or name.startswith("/"):
            return f"배포본 밖을 가리키는 파일이 있습니다: {name}"
    return ""


def candidates(root: Path, configured: str = "") -> dict[str, Any]:
    """업데이트 폴더의 배포본 — 판 순서(새것 먼저), 지금보다 새것인가 · 검사 결과."""
    folder = update_dir(root, configured)
    current = current_version(root)
    now = version_key(current)
    out = []
    reachable = folder.is_dir()
    for path in sorted(folder.glob("느린나이테-*.zip")) if reachable else []:
        key = version_key(path.stem)
        if key is None:
            continue
        out.append({"name": path.stem, "file": path.name, "size": path.stat().st_size,
                    "newer": now is None or key > now, "current": path.stem.split("-no-vendor")[0] == current,
                    "problem": "", "has_sha": _sha_file(path).is_file()})
    out.sort(key=lambda c: version_key(c["name"]) or (0, 0), reverse=True)
    for item in out[:5]:                  # 위 다섯만 검사(큰 zip 을 매번 다 읽지 않게)
        item["problem"] = verify(folder / item["file"])
    return {"folder": str(folder), "reachable": reachable, "current": current, "items": out,
            "newest": next((c["name"] for c in out if c["newer"] and not c["problem"]), "")}


# ── 예약(앱) · 적용(run.py) ──────────────────────────────────────────────────────────────────────────

def _state_path(root: Path) -> Path:
    return root / "updates" / STATE


def read_state(root: Path) -> dict[str, Any]:
    try:
        return json.loads(_state_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(root: Path, data: dict[str, Any]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def request(root: Path, zip_path: Path, by: str = "", data_backup: str = "") -> dict[str, Any]:
    """적용을 예약한다 — 다음에 run.py 가 켤 때 적용. 앱은 이 뒤에 스스로 끝난다."""
    problem = verify(zip_path)
    if problem:
        raise UpdateError(problem)
    pending = {"zip": str(zip_path), "name": zip_path.stem, "at": datetime.now().isoformat(timespec="seconds"),
               "by": by, "data_backup": data_backup, "action": "apply"}
    path = root / "updates" / PENDING
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    return pending


def request_rollback(root: Path, by: str = "") -> dict[str, Any]:
    backup = latest_rollback(root)
    if backup is None:
        raise UpdateError("되돌릴 이전 판이 없습니다.")
    pending = {"action": "rollback", "name": backup.name, "at": datetime.now().isoformat(timespec="seconds"), "by": by}
    path = root / "updates" / PENDING
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    return pending


def _manifest(folder: Path) -> list[str] | None:
    try:
        return [line.strip() for line in (folder / MANIFEST).read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return None


def _protected(rel: str) -> bool:
    return PurePosixPath(rel).parts[0] in PROTECTED


def _program_files(root: Path) -> list[str]:
    """지금 설치의 프로그램 파일 — 목록이 있으면 그것, 없으면(옛 판) 지키는 것을 뺀 모든 파일."""
    listed = _manifest(root)
    if listed is not None:
        return [rel for rel in listed if (root / rel).is_file() and not _protected(rel)]
    return sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*")
                  if p.is_file() and not _protected(str(p.relative_to(root)).replace("\\", "/"))
                  and "__pycache__" not in p.parts)


def latest_rollback(root: Path) -> Path | None:
    folder = root / "updates" / ROLLBACK_DIR
    found = [p for p in folder.iterdir() if p.is_dir()] if folder.is_dir() else []
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def apply(root: Path, zip_path: Path, log=print) -> dict[str, Any]:
    """zip 을 설치 폴더에 적용한다. 바뀌는 파일은 되돌리기 폴더에 먼저 보관한다."""
    problem = verify(zip_path)
    if problem:
        raise UpdateError(problem)
    old = current_version(root) or "개발판"
    updates = root / "updates"
    work = updates / WORK_DIR
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(work)
    new_root = work / TOP
    new_files = _manifest(new_root) or sorted(str(p.relative_to(new_root)).replace("\\", "/") for p in new_root.rglob("*") if p.is_file())
    new_files = [rel for rel in new_files if not _protected(rel)]
    old_files = _program_files(root)
    # ① 보관 — 지금 판의 프로그램 파일 전부(되돌리기는 이것으로 그대로 돌아간다)
    keep = updates / ROLLBACK_DIR / f"{old}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    for rel in old_files:
        target = keep / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    (keep / "_files.json").write_text(json.dumps({"from": old, "to": zip_path.stem, "old": old_files, "new": new_files},
                                                 ensure_ascii=False), encoding="utf-8")
    log(f"  지금 판({old}) 의 프로그램 파일 {len(old_files)}개를 보관했습니다: {keep}")
    # ② 덮어쓰기 · ③ 새 판에 없는 파일 지우기
    for rel in new_files:
        source = new_root / rel
        if source.is_file():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    removed = [rel for rel in old_files if rel not in set(new_files)]
    for rel in removed:
        try:
            (root / rel).unlink()
        except OSError:
            pass
    requirements_changed = _differs(keep / "backend/requirements.txt", root / "backend/requirements.txt")
    shutil.rmtree(work, ignore_errors=True)
    # ④ 적용한 zip 은 "적용됨" 으로
    done_dir = zip_path.parent / APPLIED_DIR
    try:
        done_dir.mkdir(parents=True, exist_ok=True)
        for item in (zip_path, _sha_file(zip_path)):
            if item.is_file():
                shutil.move(str(item), str(done_dir / item.name))
    except OSError:
        pass     # 공유 폴더에 쓸 수 없어도 적용은 끝났다 — 다음에 "지금 판" 으로 보인다
    result = {"ok": True, "from": old, "to": zip_path.stem, "at": datetime.now().isoformat(timespec="seconds"),
              "files": len(new_files), "removed": len(removed), "backup": str(keep), "requirements_changed": requirements_changed}
    log(f"  {zip_path.stem} 를 적용했습니다 — 파일 {len(new_files)}개, 지운 파일 {len(removed)}개")
    return result


def _differs(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() != b.read_bytes()
    except OSError:
        return a.exists() != b.exists()


def rollback(root: Path, log=print) -> dict[str, Any]:
    keep = latest_rollback(root)
    if keep is None:
        raise UpdateError("되돌릴 이전 판이 없습니다.")
    meta = json.loads((keep / "_files.json").read_text(encoding="utf-8"))
    for rel in meta["old"]:
        source = keep / rel
        if source.is_file():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    added = [rel for rel in meta["new"] if rel not in set(meta["old"])]
    for rel in added:
        try:
            (root / rel).unlink()
        except OSError:
            pass
    shutil.rmtree(keep, ignore_errors=True)
    log(f"  {meta['to']} → {meta['from']} 로 되돌렸습니다.")
    return {"ok": True, "action": "rollback", "from": meta["to"], "to": meta["from"], "at": datetime.now().isoformat(timespec="seconds")}


def apply_pending(root: Path, log=print) -> dict[str, Any] | None:
    """run.py 가 켤 때 — 예약된 적용 · 되돌리기가 있으면 한다. 결과는 상태 파일에. 없으면 None."""
    path = root / "updates" / PENDING
    if not path.is_file():
        return None
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return None
    path.unlink(missing_ok=True)       # 실패해도 다시 켤 때마다 같은 일을 되풀이하지 않게 먼저 지운다
    try:
        if pending.get("action") == "rollback":
            result = rollback(root, log)
        else:
            result = apply(root, Path(pending["zip"]), log)
        result.update({"by": pending.get("by", ""), "data_backup": pending.get("data_backup", "")})
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 화면에 남기고, 지금 판으로 그대로 켠다
        result = {"ok": False, "action": pending.get("action", "apply"), "to": pending.get("name", ""),
                  "at": datetime.now().isoformat(timespec="seconds"), "error": f"{type(exc).__name__}: {exc}"}
        log(f"  [오류] 업데이트를 적용하지 못했습니다 — 지금 판으로 켭니다. ({result['error']})")
    state = read_state(root)
    state["last"] = result
    state.setdefault("history", []).insert(0, result)
    state["history"] = state["history"][:20]
    _write_state(root, state)
    return result
