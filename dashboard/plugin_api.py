"""Desktop backend: /api/plugins/sabbath/* for desktop/plugin.js."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sabbath_core as core  # noqa: E402
import sabbath_store as store  # noqa: E402

router = APIRouter()


def _view() -> dict:
    with store.locked_state() as s:
        v = core.public_view(s)
        v["doctor"] = store.doctor(s)
        return v


@router.get("/state")
async def state():
    v = _view()
    v["jobs"] = store.runnable_jobs() if not v["rest"] else []
    return v


@router.post("/keep")
async def keep(body: dict):
    with store.locked_state() as s:
        s["keeping"] = bool(body.get("keeping"))
        core._log(s, time.time(), "Weekly rest on." if s["keeping"] else "Weekly rest off.")
    store.notify_desktop()
    return _view()


@router.post("/begin")
async def begin(body: dict):
    kind = "try" if body.get("try") else "now"
    seconds = core.TRY_SECONDS if kind == "try" else float(body.get("hours") or 24) * 3600
    return {"message": store.begin_now(max(60.0, min(72 * 3600.0, seconds)), kind=kind)}


@router.post("/end")
async def end():
    return {"message": store.end_now()}


@router.post("/ox")
async def ox(body: dict):
    with store.locked_state() as s:
        msg = core.ox(s, time.time(), body.get("why", ""))
    store.notify_desktop()
    return {"message": msg}


@router.post("/set-aside")
async def set_aside(body: dict):
    try:
        with store.locked_state() as s:
            item = core.set_aside(s, body.get("item", ""), time.time())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    store.notify_desktop()
    return item
