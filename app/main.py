from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import STATIC_DIR, UPLOAD_DIR
from app.db import get_db, init_db
from app.routers import auth, board, inbox, projects

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class UTF8JSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _validation_message(exc: RequestValidationError) -> str:
    for err in exc.errors():
        msg = str(err.get("msg", ""))
        if msg.startswith("Value error, "):
            return msg.removeprefix("Value error, ")
        loc = err.get("loc") or ()
        if "password" in loc and err.get("type") == "string_too_short":
            return "密码至少 8 位"
        if "display_name" in loc:
            return "请填写显示名"
    return "请求参数不正确"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="看板", default_response_class=UTF8JSONResponse, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(board.router)
app.include_router(inbox.router)


@app.middleware("http")
async def protect(request: Request, call_next):
    if request.method in UNSAFE and request.url.path.startswith("/api/") and request.headers.get("x-kanban") != "1":
        return UTF8JSONResponse({"detail": "缺少请求头"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    return UTF8JSONResponse({"detail": _validation_message(exc)}, status_code=422)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(404, "不存在")
    candidate = (STATIC_DIR / full_path).resolve()
    root = STATIC_DIR.resolve()
    if candidate.is_file() and candidate.is_relative_to(root):
        return FileResponse(candidate)
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
