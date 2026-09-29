from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import secure_cookie
from app.constants import SESSION_COOKIE, SESSION_DAYS
from app.db import get_db
from app.deps import current_user
from app.limit import limit
from app.models import User
from app.schemas import LoginIn, PasswordIn, ProfileIn, RegisterIn
from app.security import hash_password, sign_session, verify_password
from app.serialize import iso, user_brief
from app.services import create_user

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


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    limit(request, "register", 10, 3600)
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "该邮箱已注册")
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
    db.add(user)
    return profile(user)


@router.post("/password")
def change_password(body: PasswordIn, user: User = Depends(current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "当前密码不正确")
    user.password_hash = hash_password(body.new_password)
    return {"ok": True}
