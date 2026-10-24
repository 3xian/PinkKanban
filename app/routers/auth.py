from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import secure_cookie
from app.constants import SESSION_COOKIE, SESSION_DAYS
from app.db import get_db
from app.deps import current_user, session_user
from app.limit import limit
from app.mail import send_register_code
from app.models import AccessToken, User, utcnow
from app.schemas import AccessTokenIn, EmailIn, LoginIn, PasswordIn, ProfileIn, RegisterIn
from app.security import hash_access_token, hash_password, sign_session, verify_password
from app.serialize import iso, user_brief
from app.services import create_user
from app.verify import CODE_TTL, RESEND_WAIT, consume_code, issue_code

router = APIRouter(prefix="/api/auth", tags=["auth"])
_dummy: str | None = None


def profile(user: User) -> dict:
    data = user_brief(user, email=True)
    data["created_at"] = iso(user.created_at)
    return data


def _dummy_hash() -> str:
    global _dummy
    if _dummy is None:
        _dummy = hash_password("not-used-password")
    return _dummy


def set_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(user_id),
        httponly=True,
        samesite="lax",
        secure=secure_cookie(),
        max_age=SESSION_DAYS * 86400,
        path="/",
    )


@router.post("/code")
def send_code(body: EmailIn, request: Request, db: Session = Depends(get_db)):
    limit(request, "code", 8, 3600)
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "该邮箱已注册")
    code = issue_code(db, body.email)
    send_register_code(body.email, code, minutes=CODE_TTL // 60)
    return {"ok": True, "retry_after": RESEND_WAIT}

@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    limit(request, "register", 10, 3600)
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "该邮箱已注册")
    consume_code(db, body.email, body.code)
    user = create_user(db, email=body.email, password_hash=hash_password(body.password), display_name=body.display_name)
    set_session(response, user.id)
    return profile(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    limit(request, "login", 20, 600)
    user = db.scalar(select(User).where(User.email == body.email))
    ok = verify_password(body.password, user.password_hash if user else _dummy_hash())
    if user is None or not ok:
        raise HTTPException(401, "邮箱或密码不正确")
    set_session(response, user.id)
    return profile(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return profile(user)


@router.patch("/me")
def update_me(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "display_name" in data:
        user.display_name = data["display_name"]
    if "avatar_color" in data:
        user.avatar_color = data["avatar_color"]
    if "avatar_id" in data:
        user.avatar_id = data["avatar_id"]
    db.add(user)
    return profile(user)


@router.post("/password")
def change_password(body: PasswordIn, user: User = Depends(current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "当前密码不正确")
    user.password_hash = hash_password(body.new_password)
    return {"ok": True}


def token_info(token: AccessToken) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "created_at": iso(token.created_at),
        "expires_at": iso(token.expires_at),
    }


@router.get("/tokens")
def list_tokens(response: Response, user: User = Depends(session_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    tokens = db.scalars(select(AccessToken).where(AccessToken.user_id == user.id).order_by(AccessToken.id.desc()))
    return {"items": [token_info(token) for token in tokens]}


@router.post("/tokens")
def create_token(body: AccessTokenIn, response: Response, user: User = Depends(session_user), db: Session = Depends(get_db)):
    secret = "pk_" + secrets.token_urlsafe(32)
    token = AccessToken(
        user_id=user.id,
        name=body.name,
        token_hash=hash_access_token(secret),
        expires_at=utcnow() + timedelta(days=body.expires_in_days) if body.expires_in_days is not None else None,
    )
    db.add(token)
    db.flush()
    response.headers["Cache-Control"] = "no-store"
    return {**token_info(token), "token": secret}


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: int, user: User = Depends(session_user), db: Session = Depends(get_db)):
    token = db.scalar(select(AccessToken).where(AccessToken.id == token_id, AccessToken.user_id == user.id))
    if token is None:
        raise HTTPException(404, "凭证不存在")
    db.delete(token)
    return {"ok": True}
