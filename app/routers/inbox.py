from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.limit import limit
from app.models import User
from app.routers.auth import profile
from app.schemas import clean_email
from app.services import (
    accept_invite,
    list_projects,
    lookup_user,
    mark_read,
    my_cards,
    notification_list,
    quota_dict,
    read_all,
    reject_invite,
    unread_count,
)

router = APIRouter(prefix="/api", tags=["inbox"])


@router.get("/bootstrap")
def bootstrap(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {
        "user": profile(user),
        "projects": list_projects(db, user, archived=False),
        "unread": unread_count(db, user.id),
        "quota": quota_dict(db, user.id),
    }


@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return notification_list(db, user)


@router.post("/notifications/{note_id}/read")
def read_one(note_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mark_read(db, note_id, user)
    return {"ok": True}


@router.post("/notifications/read-all")
def read_every(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"ok": True, "count": read_all(db, user)}


@router.post("/notifications/{note_id}/accept")
def accept(note_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    note = accept_invite(db, note_id, user)
    return {"ok": True, "project_id": note.project_id}


@router.post("/notifications/{note_id}/reject")
def reject(note_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    reject_invite(db, note_id, user)
    return {"ok": True}


@router.get("/me/cards")
def cards(q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"cards": my_cards(db, user, q)}


@router.get("/users/lookup")
def lookup(request: Request, email: str = Query(min_length=3), user: User = Depends(current_user), db: Session = Depends(get_db)):
    limit(request, f"lookup:{user.id}", 30, 60)
    try:
        normalized = clean_email(email)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    found = lookup_user(db, normalized)
    if found is None:
        raise HTTPException(404, "该邮箱尚未注册")
    return found
