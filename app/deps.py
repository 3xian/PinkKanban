from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.constants import SESSION_COOKIE
from app.db import get_db
from app.models import AccessToken, User, utcnow
from app.security import hash_access_token, read_session


def current_user(request: Request, db: Session = Depends(get_db, scope="function")) -> User:
    authorization = request.headers.get("authorization")
    if authorization is not None:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(401, "凭证无效或已过期")
        token = db.scalar(select(AccessToken).where(
            AccessToken.token_hash == hash_access_token(parts[1]),
            or_(AccessToken.expires_at.is_(None), AccessToken.expires_at > utcnow()),
        ))
        user = db.get(User, token.user_id) if token else None
    else:
        user_id = read_session(request.cookies.get(SESSION_COOKIE))
        user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "请先登录")
    return user


def session_user(request: Request, db: Session = Depends(get_db, scope="function")) -> User:
    if "authorization" in request.headers:
        raise HTTPException(403, "请通过网页登录管理凭证")
    return current_user(request, db)
