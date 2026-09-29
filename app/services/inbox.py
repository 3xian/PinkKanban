from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BoardColumn,
    Card,
    CardAssignee,
    Notification,
    Project,
    ProjectMember,
    User,
    utcnow,
)
from app.serialize import day, iso, user_brief
from app.services.base import _users


def notification_list(db: Session, user: User) -> dict:
    rows = list(
        db.scalars(select(Notification).where(Notification.recipient_id == user.id).order_by(Notification.id.desc()).limit(80))
    )
    actors = _users(db, {row.actor_id for row in rows if row.actor_id})
    return {
        "unread": unread_count(db, user.id),
        "items": [
            {
                "id": row.id,
                "type": row.type,
                "title": row.title,
                "body": row.body,
                "status": row.status,
                "read": row.read_at is not None,
                "project_id": row.project_id,
                "card_id": row.card_id,
                "created_at": iso(row.created_at),
                "actor": user_brief(actors[row.actor_id]) if row.actor_id in actors else None,
            }
            for row in rows
        ],
    }


def unread_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(Notification).where(Notification.recipient_id == user_id, Notification.read_at.is_(None))
        )
        or 0
    )


def mark_read(db: Session, note_id: int, user: User) -> None:
    note = db.get(Notification, note_id)
    if note is None or note.recipient_id != user.id:
        raise HTTPException(404, "通知不存在")
    if note.read_at is None:
        note.read_at = utcnow()


def read_all(db: Session, user: User) -> int:
    rows = db.scalars(select(Notification).where(Notification.recipient_id == user.id, Notification.read_at.is_(None))).all()
    now = utcnow()
    for row in rows:
        row.read_at = now
    return len(rows)


def my_cards(db: Session, user: User, q: str = "") -> list[dict]:
    stmt = (
        select(Card, Project, BoardColumn)
        .join(CardAssignee, CardAssignee.card_id == Card.id)
        .join(Project, Project.id == Card.project_id)
        .join(BoardColumn, BoardColumn.id == Card.column_id)
        .join(ProjectMember, (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == user.id))
        .where(CardAssignee.user_id == user.id, Card.archived.is_(False), Project.archived.is_(False))
        .order_by(Card.due_on.is_(None), Card.due_on, Card.updated_at.desc())
        .limit(200)
    )
    query = q.strip()
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Card.title.like(f"%{escaped}%", escape="\\"))
    rows = db.execute(stmt).all()
    return [
        {
            "id": card.id,
            "title": card.title,
            "priority": card.priority,
            "due_on": day(card.due_on),
            "done": bool(card.done),
            "project_id": project.id,
            "project_name": project.name,
            "project_color": project.color,
            "column_id": column.id,
            "column_name": column.name,
        }
        for card, project, column in rows
    ]


def lookup_user(db: Session, email: str) -> dict | None:
    person = db.scalar(select(User).where(User.email == email))
    if person is None:
        return None
    return user_brief(person, email=True)
