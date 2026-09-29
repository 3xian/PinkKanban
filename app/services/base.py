from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import daily_project_limit, timezone_name
from app.constants import COLORS, ROLE_RANK
from app.models import (
    Activity,
    BoardColumn,
    Card,
    Notification,
    Project,
    ProjectCreation,
    ProjectMember,
    User,
    utcnow,
)
from app.serialize import dumps

ROLE_LABEL = {"owner": "拥有者", "admin": "管理员", "member": "成员", "viewer": "只读"}


def day_start_utc() -> datetime:
    tz = ZoneInfo(timezone_name())
    start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def quota_used(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ProjectCreation)
            .where(ProjectCreation.user_id == user_id, ProjectCreation.created_at >= day_start_utc())
        )
        or 0
    )


def quota_dict(db: Session, user_id: int) -> dict:
    used = quota_used(db, user_id)
    limit = daily_project_limit()
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}


def color_for(email: str) -> str:
    return COLORS[sum(email.encode()) % len(COLORS)]


def _touch(project: Project) -> None:
    project.updated_at = utcnow()


def _activity(db: Session, *, project_id: int, user_id: int, action: str, card_id: int | None = None, detail: dict | None = None) -> None:
    db.add(Activity(project_id=project_id, card_id=card_id, user_id=user_id, action=action, detail=dumps(detail or {})))


def _notify(
    db: Session,
    *,
    recipient_id: int,
    actor_id: int | None,
    type: str,
    title: str,
    body: str,
    project_id: int | None = None,
    card_id: int | None = None,
    status: str = "info",
    payload: dict | None = None,
) -> Notification | None:
    if actor_id is not None and recipient_id == actor_id:
        return None
    note = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        type=type,
        title=title,
        body=body,
        project_id=project_id,
        card_id=card_id,
        status=status,
        payload=dumps(payload or {}),
    )
    db.add(note)
    return note


def _users(db: Session, ids: set[int] | list[int]) -> dict[int, User]:
    wanted = [item for item in ids if item]
    if not wanted:
        return {}
    return {user.id: user for user in db.scalars(select(User).where(User.id.in_(wanted)))}


def require_access(db: Session, project_id: int, user: User, minimum: str = "viewer", *, write: bool = False) -> tuple[Project, ProjectMember]:
    member = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
    )
    project = db.get(Project, project_id) if member else None
    if member is None or project is None:
        raise HTTPException(404, "项目不存在")
    if ROLE_RANK[member.role] < ROLE_RANK[minimum]:
        raise HTTPException(403, "没有权限执行此操作")
    if write and project.archived:
        raise HTTPException(409, "项目已归档")
    return project, member


def _lock_project(db: Session, project_id: int) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if project is None:
        raise HTTPException(404, "项目不存在")
    return project


def begin_write(db: Session, project_id: int, user: User, minimum: str = "member") -> tuple[Project, ProjectMember]:
    project, member = require_access(db, project_id, user, minimum, write=True)
    locked = _lock_project(db, project_id)
    if locked.archived:
        raise HTTPException(409, "项目已归档")
    return locked, member


def _require_card(db: Session, card_id: int, user: User, minimum: str = "viewer", *, write: bool = False) -> tuple[Card, Project, ProjectMember]:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(404, "卡片不存在")
    project, member = require_access(db, card.project_id, user, minimum, write=write)
    return card, project, member


def _columns(db: Session, project_id: int) -> list[BoardColumn]:
    return list(
        db.scalars(select(BoardColumn).where(BoardColumn.project_id == project_id).order_by(BoardColumn.position, BoardColumn.id))
    )


def _live_cards(db: Session, column_id: int, exclude: int | None = None) -> list[Card]:
    cards = list(
        db.scalars(
            select(Card)
            .where(Card.column_id == column_id, Card.archived.is_(False))
            .order_by(Card.position, Card.id)
        )
    )
    if exclude is None:
        return cards
    return [card for card in cards if card.id != exclude]


def _reindex(cards: list[Card]) -> None:
    for index, card in enumerate(cards):
        card.position = index


def _column_ids(db: Session, project_id: int) -> dict:
    return {"column_ids": [column.id for column in _columns(db, project_id)]}


def _member_ids(db: Session, project_id: int) -> set[int]:
    return set(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)))


def mentioned_ids(text: str, users: list[User]) -> list[int]:
    occupied = [False] * len(text)
    found: list[int] = []
    for person in sorted(users, key=lambda item: len(item.display_name or ""), reverse=True):
        name = (person.display_name or "").strip()
        if not name:
            continue
        token = "@" + name
        start = 0
        while True:
            index = text.find(token, start)
            if index < 0:
                break
            end = index + len(token)
            boundary = end == len(text) or text[end] in " \n\t,，。！？、；;:："
            if boundary and not any(occupied[index:end]):
                occupied[index:end] = [True] * (end - index)
                found.append(person.id)
            start = index + len(token)
    return found
