from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.constants import SESSION_COOKIE
from app.db import get_db
from app.models import User
from app.security import read_session


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = read_session(request.cookies.get(SESSION_COOKIE))
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "请先登录")
    return user
