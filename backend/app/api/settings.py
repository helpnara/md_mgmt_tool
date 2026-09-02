from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import settings as svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    author: str | None = None


@router.get("")
def read_settings() -> dict:
    return svc.load()


@router.put("")
def update_settings(payload: SettingsUpdate) -> dict:
    return svc.save(payload.model_dump())
