from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import User
from app.schemas import InviteIn, ProjectIn, ProjectPatch, RoleIn, TransferIn
from app.services import (
    activity_list,
    cancel_invite,
    create_project,
    delete_project,
    invite_member,
    leave_project,
    list_projects,
    project_detail,
    quota_dict,
    remove_member,
    set_archived,
    transfer_project,
    update_member,
    update_project,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def index(archived: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"projects": list_projects(db, user, archived=archived), "quota": quota_dict(db, user.id)}


@router.post("")
def create(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = create_project(db, user, body.name, body.description, body.color)
    return {**project_detail(db, project.id, user), "quota": quota_dict(db, user.id)}


@router.get("/{project_id}")
def detail(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return project_detail(db, project_id, user)


@router.patch("/{project_id}")
def update(project_id: int, body: ProjectPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    update_project(db, project_id, user, body.model_dump(exclude_unset=True))
    return project_detail(db, project_id, user)


@router.post("/{project_id}/archive")
def archive(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    set_archived(db, project_id, user, True)
    return {"ok": True}


@router.post("/{project_id}/restore")
def restore(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    set_archived(db, project_id, user, False)
    return project_detail(db, project_id, user)


@router.delete("/{project_id}")
def remove(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    delete_project(db, project_id, user)
    return {"ok": True}


@router.post("/{project_id}/transfer")
def transfer(project_id: int, body: TransferIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    transfer_project(db, project_id, user, body.user_id)
    return project_detail(db, project_id, user)


@router.post("/{project_id}/invites")
def invite(project_id: int, body: InviteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    invite_member(db, project_id, user, body.email, body.role)
    return project_detail(db, project_id, user)


@router.post("/{project_id}/invites/{note_id}/cancel")
def cancel(project_id: int, note_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cancel_invite(db, project_id, note_id, user)
    return project_detail(db, project_id, user)


@router.patch("/{project_id}/members/{member_id}")
def role(project_id: int, member_id: int, body: RoleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    update_member(db, project_id, member_id, user, body.role)
    return project_detail(db, project_id, user)


@router.delete("/{project_id}/members/{member_id}")
def kick(project_id: int, member_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    remove_member(db, project_id, member_id, user)
    return project_detail(db, project_id, user)


@router.post("/{project_id}/leave")
def leave(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    leave_project(db, project_id, user)
    return {"ok": True}


@router.get("/{project_id}/activity")
def activity(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return activity_list(db, project_id, user)
