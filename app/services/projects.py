from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, daily_project_limit
from app.constants import COLORS, DEFAULT_COLUMNS, DEFAULT_LABELS, ROLE_RANK
from app.db import defer_unlink
from app.models import (
    Activity,
    Attachment,
    BoardColumn,
    Card,
    Label,
    Notification,
    Project,
    ProjectCreation,
    ProjectMember,
    User,
    utcnow,
)
from app.serialize import dumps, iso, loads, project_brief, user_brief
from app.services.base import (
    ROLE_LABEL,
    _activity,
    _notify,
    _lock_project,
    _touch,
    _users,
    begin_write,
    color_for,
    quota_used,
    require_access,
)
from app.services.members import _member_rows


def create_user(db: Session, *, email: str, password_hash: str, display_name: str) -> User:
    user = User(email=email, password_hash=password_hash, display_name=display_name, avatar_color=color_for(email))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "该邮箱已注册") from exc
    return user


def list_projects(db: Session, user: User, *, archived: bool) -> list[dict]:
    rows = db.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id, Project.archived.is_(archived))
        .order_by(Project.updated_at.desc(), Project.id.desc())
    ).all()
    ids = [project.id for project, _role in rows]
    members = _grouped_count(db, ProjectMember.project_id, ids)
    cards = _grouped_count(db, Card.project_id, ids, Card.archived.is_(False))
    result = []
    for project, role in rows:
        item = project_brief(project)
        item.update({"role": role, "member_count": members.get(project.id, 0), "open_cards": cards.get(project.id, 0)})
        result.append(item)
    return result


def _grouped_count(db: Session, column, ids: list[int], extra=None) -> dict[int, int]:
    if not ids:
        return {}
    stmt = select(column, func.count()).where(column.in_(ids))
    if extra is not None:
        stmt = stmt.where(extra)
    return {key: int(value) for key, value in db.execute(stmt.group_by(column))}


def project_detail(db: Session, project_id: int, user: User) -> dict:
    project, member = require_access(db, project_id, user)
    people = _member_rows(db, project.id)
    invites = []
    if ROLE_RANK[member.role] >= ROLE_RANK["admin"]:
        notes = db.scalars(
            select(Notification)
            .where(
                Notification.project_id == project.id,
                Notification.type == "project_invite",
                Notification.status == "pending",
            )
            .order_by(Notification.id.desc())
        ).all()
        recipients = _users(db, {note.recipient_id for note in notes})
        for note in notes:
            person = recipients.get(note.recipient_id)
            payload = loads(note.payload)
            invites.append(
                {
                    "id": note.id,
                    "email": person.email if person else payload.get("email", ""),
                    "display_name": person.display_name if person else "",
                    "avatar_color": person.avatar_color if person else COLORS[0],
                    "role": payload.get("role", "member"),
                    "created_at": iso(note.created_at),
                }
            )
    return {"project": project_brief(project), "role": member.role, "members": people, "invites": invites}



def create_project(db: Session, user: User, name: str, description: str, color: str) -> Project:
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if quota_used(db, user.id) >= daily_project_limit():
        raise HTTPException(429, f"今天最多创建 {daily_project_limit()} 个项目，明天再来")
    project = Project(name=name, description=description, color=color, owner_id=user.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    db.add(ProjectCreation(user_id=user.id, project_id=project.id))
    for index, column_name in enumerate(DEFAULT_COLUMNS):
        db.add(BoardColumn(project_id=project.id, name=column_name, color=COLORS[index % len(COLORS)], position=index))
    for label_name, label_color in DEFAULT_LABELS:
        db.add(Label(project_id=project.id, name=label_name, color=label_color))
    _activity(db, project_id=project.id, user_id=user.id, action="project.created", detail={"name": name})
    _notify(
        db,
        recipient_id=user.id,
        actor_id=None,
        type="project_created",
        title="项目已创建",
        body=f"你创建了「{name}」",
        project_id=project.id,
    )
    db.flush()
    return project


def update_project(db: Session, project_id: int, user: User, data: dict) -> None:
    project, _member = begin_write(db, project_id, user, "admin")
    if "name" in data:
        project.name = data["name"]
    if "description" in data:
        project.description = data["description"]
    if "color" in data:
        project.color = data["color"]
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="project.updated", detail={"fields": list(data)})


def set_archived(db: Session, project_id: int, user: User, archived: bool) -> None:
    project, _member = require_access(db, project_id, user, "admin")
    project = _lock_project(db, project_id)
    project.archived = archived
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="project.archived" if archived else "project.restored")


def delete_project(db: Session, project_id: int, user: User) -> None:
    project, _member = require_access(db, project_id, user, "owner")
    _lock_project(db, project_id)
    rows = db.scalars(select(Attachment).join(Card, Attachment.card_id == Card.id).where(Card.project_id == project_id)).all()
    for row in rows:
        defer_unlink(db, UPLOAD_DIR / row.stored_name)
    db.delete(project)


def transfer_project(db: Session, project_id: int, user: User, target_id: int) -> None:
    project, owner = require_access(db, project_id, user, "owner")
    if target_id == user.id:
        raise HTTPException(400, "你已经是拥有者")
    target = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == target_id)
    )
    if target is None:
        raise HTTPException(404, "对方不在项目中")
    project = _lock_project(db, project_id)
    target.role = "owner"
    owner.role = "admin"
    project.owner_id = target_id
    _touch(project)
    person = db.get(User, target_id)
    _activity(db, project_id=project.id, user_id=user.id, action="project.transferred", detail={"name": person.display_name if person else ""})
    _notify(
        db,
        recipient_id=target_id,
        actor_id=user.id,
        type="project_transferred",
        title="你成为了拥有者",
        body=f"你现在拥有项目「{project.name}」",
        project_id=project.id,
    )


def _activity_item(item: Activity, actors: dict[int, User]) -> dict:
    person = actors.get(item.user_id)
    return {
        "id": item.id,
        "action": item.action,
        "detail": loads(item.detail),
        "created_at": iso(item.created_at),
        "card_id": item.card_id,
        "user": user_brief(person) if person else None,
    }


def activity_list(db: Session, project_id: int, user: User) -> dict:
    require_access(db, project_id, user)
    rows = list(db.scalars(select(Activity).where(Activity.project_id == project_id).order_by(Activity.id.desc()).limit(80)))
    actors = _users(db, {row.user_id for row in rows})
    return {"items": [_activity_item(row, actors) for row in rows]}
