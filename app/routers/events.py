from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.db import session_factory
from app.deps import current_user
from app.live import board_events
from app.services.base import require_access

router = APIRouter(prefix="/api", tags=["board"])
HEARTBEAT_SECONDS = 15


def authorize(request: Request, project_id: int):
    # Authentication and permission checks never hold a DB connection while idle.
    with session_factory()() as db:
        user = current_user(request, db)
        require_access(db, project_id, user)


async def changes(request: Request, project_id: int):
    with board_events.subscribe(project_id) as queue:
        # Every connection requests a snapshot, covering changes during reconnect.
        yield 'retry: 3000\nevent: ready\ndata: {}\n\n'
        while not await request.is_disconnected():
            changed = True
            try:
                await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                changed = False
            try:
                await run_in_threadpool(authorize, request, project_id)
            except HTTPException:
                yield 'event: unavailable\ndata: {}\n\n'
                return
            yield 'event: change\ndata: {}\n\n' if changed else ': keepalive\n\n'


@router.get("/projects/{project_id}/events")
async def events(request: Request, project_id: int):
    await run_in_threadpool(authorize, request, project_id)
    return StreamingResponse(changes(request, project_id), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-store",
        "X-Accel-Buffering": "no",
    })
