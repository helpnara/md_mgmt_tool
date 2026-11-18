"""팀 역량 · 기술 스택 (TODO 284) — 팀장 · 관리자만."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from .. import who
from ..deps import get_db
from ..services import settings as settings_service
from ..services import team_skills as svc

router = APIRouter(prefix="/api/team-skills", tags=["team-skills"])


@router.get("")
def overview(request: Request, period: str = Query("3y", pattern="^(3y|year|all)$"), left: bool = False, conn=Depends(get_db)):
    if not who.of(request).manages:
        raise HTTPException(status_code=403, detail="팀 역량은 팀장 · 관리자만 봅니다.")
    # 292 G — 해가 바뀐 뒤 처음 열면 지난해 기록을 저절로 한 벌, 그리고 지난해 기록 ↔ 지금
    from ..services import team_snapshots as snaps

    try:
        snaps.ensure_last_year(conn)
    except Exception:  # noqa: BLE001 — 기록을 못 남겨도 화면은 연다
        pass
    view = svc.overview(conn, period, left)
    view["snapshots"] = snaps.listing()
    view["snapshot_compare"] = snaps.last_year_compare(view)
    return view


@router.put("/targets")
def save_targets(request: Request, targets: list[dict] = Body(..., embed=True)):
    """목표 역량 · 보유 기술 (TODO 284 2단계) — 설정 `team_skill_targets`. 팀장 PC 에서도 저장한다(설정 화면은 서버 PC 만)."""
    if not who.of(request).manages:
        raise HTTPException(status_code=403, detail="팀 역량은 팀장 · 관리자만 봅니다.")
    try:
        settings_service.save({"team_skill_targets": targets})
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    return {"targets": settings_service.load().get("team_skill_targets") or []}



def _manager(request: Request) -> who.User:
    user = who.of(request)
    if not user.manages:
        raise HTTPException(status_code=403, detail="팀 역량은 팀장 · 관리자만 봅니다.")
    return user


# ── 292 G 해마다 남기는 기록 ─────────────────────────────────────────────────
@router.post("/snapshots")
def save_snapshot(request: Request, year: str = Body("", embed=True), conn=Depends(get_db)):
    from ..services import team_snapshots as snaps

    user = _manager(request)
    try:
        return snaps.save(conn, year or None, by=user.name or "팀장")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@router.get("/snapshots/{year}")
def read_snapshot(request: Request, year: str):
    from ..services import team_snapshots as snaps

    _manager(request)
    try:
        found = snaps.read(year)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    if not found:
        raise HTTPException(status_code=404, detail=f"{year}년 기록이 없습니다.")
    return found


# ── 292 B 승계 · 짝 계획 ─────────────────────────────────────────────────────
@router.get("/succession")
def list_plans(request: Request):
    from ..services import team_plans

    _manager(request)
    return team_plans.plans()


@router.post("/succession", status_code=201)
def add_plan(request: Request, plan: dict = Body(...)):
    from ..services import team_plans

    user = _manager(request)
    try:
        return team_plans.add_plan(plan, by=user.name or "팀장")
    except team_plans.PlanError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@router.patch("/succession/{plan_id}")
def update_plan(request: Request, plan_id: str, plan: dict = Body(...)):
    from ..services import team_plans

    _manager(request)
    try:
        return team_plans.update_plan(plan_id, plan)
    except team_plans.PlanError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    except KeyError:
        raise HTTPException(status_code=404, detail="그 계획이 없습니다.") from None


@router.delete("/succession/{plan_id}", status_code=204)
def delete_plan(request: Request, plan_id: str):
    from ..services import team_plans

    _manager(request)
    try:
        team_plans.delete_plan(plan_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="그 계획이 없습니다.") from None


@router.get("/reminders")
def reminders(request: Request):
    """홈 할 일 (292 G · B) — 12월에 올해 기록이 없으면 · 기한 지난 승계 계획. 팀장 홈이 부른다."""
    from .. import clock
    from ..services import team_plans
    from ..services import team_snapshots as snaps

    _manager(request)
    today = clock.today()
    year = str(today.year)
    snapshot_due = today.month == 12 and not any(item["year"] == year for item in snaps.listing())
    overdue = [p for p in team_plans.plans()["plans"] if p.get("overdue")]
    return {"snapshot_due": snapshot_due, "year": year,
            "overdue": [{"id": p["id"], "kind": p["kind"], "name": p["name"], "learner": p["learner"], "due": p["due"]} for p in overdue]}
