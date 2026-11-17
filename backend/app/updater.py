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
import os
import shutil
import time
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
KEEP_APPLIED = 3      # 302 — `적용됨` 에 남길 판 수(zip + .sha256 한 쌍씩)
KEEP_ROLLBACK = 2     # 302 — `되돌리기` 에 남길 개수([이전 판으로]는 가장 최근 것을 쓴다)


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
            "local": is_local(root, folder), "usage": usage(root),
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


def _rollback_dirs(root: Path) -> list[Path]:
    """되돌리기 보관본 — 오래된 것부터. 이름 끝의 시각(YYYYMMDDHHMMSS)으로 줄 세운다(폴더 시각은 윈도우에서 흔들린다)."""
    folder = root / "updates" / ROLLBACK_DIR
    found = [p for p in folder.iterdir() if p.is_dir() and (p / "_files.json").is_file()] if folder.is_dir() else []
    return sorted(found, key=lambda p: (p.name[-14:], p.stat().st_mtime))


def latest_rollback(root: Path) -> Path | None:
    found = _rollback_dirs(root)
    return found[-1] if found else None


# ── 쌓이는 파일 정리 (TODO 302) ─────────────────────────────────────────────────────────────────────

def is_local(root: Path, folder: Path) -> bool:
    """설치 폴더의 `updates` 인가 — 아니면(설정에서 정한 사내 공유 폴더) 그 안의 zip 은 옮기지도 지우지도 않는다.
    여러 팀장 서버가 같은 공유 폴더를 볼 때 먼저 적용한 서버가 zip 을 옮겨 다른 서버에 새 판이 안 보이던 일을 막는다."""
    try:
        return folder.resolve() == (root / "updates").resolve()
    except OSError:
        return False


def _move(src: Path, dst: Path) -> str:
    """옮긴다(같은 이름이 있으면 바꿔 넣는다). 잠깐 잡혀 있으면(탐색기 미리보기 · 백신 검사) 몇 번 다시. 실패면 까닭."""
    error = ""
    for _ in range(4):
        try:
            os.replace(src, dst)
            return ""
        except OSError as exc:
            error = str(exc)
            try:                          # 다른 드라이브 등 — 복사한 뒤 지운다
                shutil.copy2(src, dst)
                src.unlink()
                return ""
            except OSError as exc2:
                error = str(exc2)
                time.sleep(0.5)
    return error


def _remove(path: Path) -> None:
    try:
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    except OSError:
        pass


def tidy(root: Path) -> list[str]:
    """설치 폴더 `updates` 정리 — 짝 잃은 .sha256 · 오래된 `적용됨` 쌍 · 오래된 `되돌리기`. 지운 이름을 돌려준다."""
    updates = root / "updates"
    removed: list[str] = []
    if not updates.is_dir():
        return removed
    # ① zip 없이 남은 .sha256 (updates · 적용됨)
    for folder in (updates, updates / APPLIED_DIR):
        if folder.is_dir():
            for sha in folder.glob("*.zip.sha256"):
                if not sha.with_name(sha.name[: -len(".sha256")]).is_file():
                    _remove(sha)
                    removed.append(str(sha.relative_to(updates)))
    # ② 적용됨 — 최근 KEEP_APPLIED 판만
    applied = updates / APPLIED_DIR
    if applied.is_dir():
        zips = sorted((z for z in applied.glob("느린나이테-*.zip") if version_key(z.stem)), key=lambda z: version_key(z.stem))
        for old in zips[:-KEEP_APPLIED] if len(zips) > KEEP_APPLIED else []:
            for item in (old, _sha_file(old)):
                if item.exists():
                    _remove(item)
                    removed.append(str(item.relative_to(updates)))
    # ③ 되돌리기 — 최근 KEEP_ROLLBACK 개만
    dirs = _rollback_dirs(root)
    for old in dirs[:-KEEP_ROLLBACK] if len(dirs) > KEEP_ROLLBACK else []:
        _remove(old)
        removed.append(str(old.relative_to(updates)))
    return removed


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def usage(root: Path) -> dict[str, Any]:
    """업데이트 폴더가 쓰는 공간 — 카드의 한 줄."""
    updates = root / "updates"
    applied = sorted((updates / APPLIED_DIR).glob("느린나이테-*.zip")) if (updates / APPLIED_DIR).is_dir() else []
    dirs = _rollback_dirs(root)
    return {"applied": len(applied), "applied_bytes": sum(_size(z) + (_size(_sha_file(z)) if _sha_file(z).is_file() else 0) for z in applied),
            "rollback": len(dirs), "rollback_bytes": sum(_size(d) for d in dirs),
            "keep_applied": KEEP_APPLIED, "keep_rollback": KEEP_ROLLBACK}


def _noop(stage: str, done: int = 0, total: int = 0) -> None:
    return None


def _each(items: list[str], stage: str, progress) -> Any:
    """하나씩 내주며 진행을 알린다 — 너무 잦지 않게(많으면 2% 마다)."""
    total = len(items)
    step = max(1, total // 50)
    for index, item in enumerate(items):
        if index % step == 0:
            progress(stage, index, total)
        yield item
    progress(stage, total, total)


def peek_pending(root: Path) -> dict[str, Any] | None:
    """예약된 일이 있나 — run.py 가 적용 전에 진행 창구를 열지 정할 때(TODO 300)."""
    path = root / "updates" / PENDING
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


def apply(root: Path, zip_path: Path, log=print, progress=_noop) -> dict[str, Any]:
    """zip 을 설치 폴더에 적용한다. 바뀌는 파일은 되돌리기 폴더에 먼저 보관한다.

    progress(단계, 한 것, 전체) — verify · extract · keep · copy · clean (TODO 300, 화면의 진행 표시)."""
    progress("verify")
    problem = verify(zip_path)
    if problem:
        raise UpdateError(problem)
    old = current_version(root) or "개발판"
    updates = root / "updates"
    work = updates / WORK_DIR
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    progress("extract")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(work)
    new_root = work / TOP
    new_files = _manifest(new_root) or sorted(str(p.relative_to(new_root)).replace("\\", "/") for p in new_root.rglob("*") if p.is_file())
    new_files = [rel for rel in new_files if not _protected(rel)]
    old_files = _program_files(root)
    # ① 보관 — 지금 판의 프로그램 파일 전부(되돌리기는 이것으로 그대로 돌아간다)
    keep = updates / ROLLBACK_DIR / f"{old}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    for rel in _each(old_files, "keep", progress):
        target = keep / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    (keep / "_files.json").write_text(json.dumps({"from": old, "to": zip_path.stem, "old": old_files, "new": new_files},
                                                 ensure_ascii=False), encoding="utf-8")
    log(f"  지금 판({old}) 의 프로그램 파일 {len(old_files)}개를 보관했습니다: {keep}")
    # ② 덮어쓰기 · ③ 새 판에 없는 파일 지우기
    for rel in _each(new_files, "copy", progress):
        source = new_root / rel
        if source.is_file():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    progress("clean")
    removed = [rel for rel in old_files if rel not in set(new_files)]
    for rel in removed:
        try:
            (root / rel).unlink()
        except OSError:
            pass
    requirements_changed = _differs(keep / "backend/requirements.txt", root / "backend/requirements.txt")
    shutil.rmtree(work, ignore_errors=True)
    # ④ 적용한 zip · .sha256 은 "적용됨" 으로 — 설치 폴더의 updates 일 때만(공유 폴더는 그대로, TODO 302)
    leftover: list[str] = []
    if is_local(root, zip_path.parent):
        done_dir = zip_path.parent / APPLIED_DIR
        try:
            done_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            leftover.append(f"{done_dir.name}: {exc}")
        for item in (zip_path, _sha_file(zip_path)):
            if item.is_file() and done_dir.is_dir():
                problem = _move(item, done_dir / item.name)
                if problem:
                    leftover.append(f"{item.name}: {problem}")
                    log(f"  [알림] {item.name} 를 '{APPLIED_DIR}' 로 옮기지 못했습니다 — {problem} (다음에 켤 때 다시 정리합니다)")
    else:
        log(f"  업데이트 폴더가 공유 폴더라 {zip_path.name} 는 그대로 둡니다(다른 서버도 쓸 수 있게).")
    cleaned = tidy(root)
    result = {"ok": True, "from": old, "to": zip_path.stem, "at": datetime.now().isoformat(timespec="seconds"),
              "files": len(new_files), "removed": len(removed), "backup": str(keep), "requirements_changed": requirements_changed,
              "leftover": leftover, "cleaned": cleaned}
    log(f"  {zip_path.stem} 를 적용했습니다 — 파일 {len(new_files)}개, 지운 파일 {len(removed)}개")
    return result


def _differs(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() != b.read_bytes()
    except OSError:
        return a.exists() != b.exists()


def rollback(root: Path, log=print, progress=_noop) -> dict[str, Any]:
    keep = latest_rollback(root)
    if keep is None:
        raise UpdateError("되돌릴 이전 판이 없습니다.")
    meta = json.loads((keep / "_files.json").read_text(encoding="utf-8"))
    for rel in _each(meta["old"], "restore", progress):
        source = keep / rel
        if source.is_file():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    progress("clean")
    added = [rel for rel in meta["new"] if rel not in set(meta["old"])]
    for rel in added:
        try:
            (root / rel).unlink()
        except OSError:
            pass
    shutil.rmtree(keep, ignore_errors=True)
    log(f"  {meta['to']} → {meta['from']} 로 되돌렸습니다.")
    return {"ok": True, "action": "rollback", "from": meta["to"], "to": meta["from"], "at": datetime.now().isoformat(timespec="seconds")}


def apply_pending(root: Path, log=print, progress=_noop) -> dict[str, Any] | None:
    """run.py 가 켤 때 — 예약된 적용 · 되돌리기가 있으면 한다. 결과는 상태 파일에. 없으면 None."""
    path = root / "updates" / PENDING
    if not path.is_file():
        try:
            tidy(root)        # 302 — 켤 때마다 지난번에 옮기지 못한 짝 잃은 .sha256 등을 정리
        except OSError:
            pass
        return None
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return None
    path.unlink(missing_ok=True)       # 실패해도 다시 켤 때마다 같은 일을 되풀이하지 않게 먼저 지운다
    try:
        if pending.get("action") == "rollback":
            result = rollback(root, log, progress)
        else:
            result = apply(root, Path(pending["zip"]), log, progress)
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
