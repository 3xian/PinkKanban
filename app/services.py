from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, daily_project_limit, timezone_name
from app.constants import (
    ALLOWED_EXTENSIONS,
    ASSIGNABLE_ROLES,
    COLORS,
    DEFAULT_COLUMNS,
    DEFAULT_LABELS,
    MAX_CARDS,
    MAX_COLUMNS,
    MAX_UPLOAD_BYTES,
    ROLE_RANK,
)
from app.db import defer_unlink
from app.models import (
    Activity,
    Attachment,
    BoardColumn,
    Card,
    CardAssignee,
    CardLabel,
    Checklist,
    ChecklistItem,
    Comment,
    Label,
    Notification,
    Project,
    ProjectCreation,
    ProjectMember,
    User,
    utcnow,
)
from app.serialize import day, dumps, excerpt, iso, loads, project_brief, user_brief

ROLE_LABEL = {"owner": "拥有者", "admin": "管理员", "member": "成员", "viewer": "只读"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


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


def _member_rows(db: Session, project_id: int) -> list[dict]:
    rows = db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.joined_at, ProjectMember.id)
    ).all()
    result = []
    for member, person in rows:
        item = user_brief(person, email=True)
        item["role"] = member.role
        result.append(item)
    return result


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
    require_access(db, project_id, user, "owner")
    _lock_project(db, project_id)
    rows = db.scalars(select(Attachment).join(Card, Attachment.card_id == Card.id).where(Card.project_id == project_id)).all()
    for row in rows:
        defer_unlink(db, UPLOAD_DIR / row.stored_name)
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "项目不存在")
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


def invite_member(db: Session, project_id: int, user: User, email: str, role: str) -> None:
    project, _member = begin_write(db, project_id, user, "admin")
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(400, "不能把对方设为拥有者")
    target = db.scalar(select(User).where(User.email == email))
    if target is None:
        raise HTTPException(404, "该邮箱尚未注册")
    if target.id == user.id:
        raise HTTPException(400, "不能邀请自己")
    existing = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == target.id)
    )
    if existing:
        raise HTTPException(409, "对方已在项目中")
    pending = db.scalar(
        select(Notification).where(
            Notification.project_id == project.id,
            Notification.recipient_id == target.id,
            Notification.type == "project_invite",
            Notification.status == "pending",
        )
    )
    if pending:
        raise HTTPException(409, "已发送邀请，等待对方批准")
    _notify(
        db,
        recipient_id=target.id,
        actor_id=user.id,
        type="project_invite",
        title="项目邀请",
        body=f"{user.display_name} 邀请你以{ROLE_LABEL[role]}身份加入「{project.name}」",
        project_id=project.id,
        status="pending",
        payload={"role": role, "email": email},
    )
    _activity(db, project_id=project.id, user_id=user.id, action="invite.sent", detail={"email": email, "role": role})


def cancel_invite(db: Session, project_id: int, note_id: int, user: User) -> None:
    project, member = begin_write(db, project_id, user, "admin")
    note = db.scalar(select(Notification).where(Notification.id == note_id).with_for_update())
    if note is None or note.project_id != project.id or note.type != "project_invite":
        raise HTTPException(404, "邀请不存在")
    if note.status != "pending":
        raise HTTPException(409, "这条邀请已经处理过了")
    if note.actor_id != user.id and ROLE_RANK[member.role] < ROLE_RANK["admin"]:
        raise HTTPException(403, "没有权限撤回邀请")
    note.status = "cancelled"
    note.body = f"加入「{project.name}」的邀请已撤回"
    _activity(db, project_id=project.id, user_id=user.id, action="invite.cancelled", detail={"email": loads(note.payload).get("email", "")})


def accept_invite(db: Session, note_id: int, user: User) -> Notification:
    note = db.scalar(select(Notification).where(Notification.id == note_id).with_for_update())
    if note is None or note.recipient_id != user.id:
        raise HTTPException(404, "通知不存在")
    if note.type != "project_invite":
        raise HTTPException(400, "这条通知不需要批准")
    if note.status != "pending":
        raise HTTPException(409, "这条邀请已经处理过了")
    project = db.get(Project, note.project_id) if note.project_id else None
    if project is None:
        note.status = "cancelled"
        raise HTTPException(404, "项目已不存在")
    if project.archived:
        raise HTTPException(409, "项目已归档")
    role = loads(note.payload).get("role", "member")
    if role not in ASSIGNABLE_ROLES:
        role = "member"
    existing = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
    )
    if existing is None:
        db.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
    note.status = "accepted"
    note.read_at = utcnow()
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="member.joined", detail={"name": user.display_name, "role": role})
    if note.actor_id:
        _notify(
            db,
            recipient_id=note.actor_id,
            actor_id=user.id,
            type="invite_accepted",
            title="邀请已接受",
            body=f"{user.display_name} 加入了「{project.name}」",
            project_id=project.id,
        )
    return note


def reject_invite(db: Session, note_id: int, user: User) -> None:
    note = db.scalar(select(Notification).where(Notification.id == note_id).with_for_update())
    if note is None or note.recipient_id != user.id:
        raise HTTPException(404, "通知不存在")
    if note.type != "project_invite":
        raise HTTPException(400, "这条通知不能拒绝")
    if note.status != "pending":
        raise HTTPException(409, "这条邀请已经处理过了")
    note.status = "rejected"
    note.read_at = utcnow()
    project = db.get(Project, note.project_id) if note.project_id else None
    if note.actor_id and project is not None:
        _notify(
            db,
            recipient_id=note.actor_id,
            actor_id=user.id,
            type="invite_rejected",
            title="邀请被拒绝",
            body=f"{user.display_name} 拒绝了「{project.name}」的邀请",
            project_id=project.id,
        )


def update_member(db: Session, project_id: int, target_id: int, user: User, role: str) -> None:
    project, actor = begin_write(db, project_id, user, "admin")
    target = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == target_id)
    )
    if target is None:
        raise HTTPException(404, "成员不存在")
    if target.role == "owner" or target_id == project.owner_id:
        raise HTTPException(400, "不能更改拥有者，请先移交项目")
    if target_id == user.id:
        raise HTTPException(400, "不能更改自己的角色")
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(400, "角色无效")
    target.role = role
    person = db.get(User, target_id)
    _activity(
        db,
        project_id=project.id,
        user_id=user.id,
        action="member.role",
        detail={"name": person.display_name if person else "", "role": role},
    )


def remove_member(db: Session, project_id: int, target_id: int, user: User) -> None:
    project, _actor = begin_write(db, project_id, user, "admin")
    target = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == target_id)
    )
    if target is None:
        raise HTTPException(404, "成员不存在")
    if target.role == "owner":
        raise HTTPException(400, "不能移除拥有者")
    person = db.get(User, target_id)
    db.delete(target)
    _clear_assignee(db, project.id, target_id)
    _activity(db, project_id=project.id, user_id=user.id, action="member.removed", detail={"name": person.display_name if person else ""})


def leave_project(db: Session, project_id: int, user: User) -> None:
    project, member = require_access(db, project_id, user)
    if member.role == "owner":
        raise HTTPException(400, "拥有者不能退出，请先移交项目")
    project = _lock_project(db, project_id)
    db.delete(member)
    _clear_assignee(db, project.id, user.id)
    _activity(db, project_id=project.id, user_id=user.id, action="member.left", detail={"name": user.display_name})


def _clear_assignee(db: Session, project_id: int, user_id: int) -> None:
    rows = db.scalars(
        select(CardAssignee).join(Card, Card.id == CardAssignee.card_id).where(Card.project_id == project_id, CardAssignee.user_id == user_id)
    ).all()
    for row in rows:
        db.delete(row)


def create_column(db: Session, project_id: int, user: User, name: str, color: str, wip_limit: int | None) -> BoardColumn:
    project, _member = begin_write(db, project_id, user)
    columns = _columns(db, project.id)
    if len(columns) >= MAX_COLUMNS:
        raise HTTPException(400, "列表数量已达上限")
    column = BoardColumn(project_id=project.id, name=name, color=color, wip_limit=wip_limit, position=len(columns))
    db.add(column)
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="column.created", detail={"name": name})
    db.flush()
    return column


def update_column(db: Session, column_id: int, user: User, data: dict) -> BoardColumn:
    column = db.get(BoardColumn, column_id)
    if column is None:
        raise HTTPException(404, "列表不存在")
    project, _member = begin_write(db, column.project_id, user)
    if "name" in data:
        column.name = data["name"]
    if "color" in data:
        column.color = data["color"]
    if "wip_limit" in data:
        column.wip_limit = data["wip_limit"]
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="column.updated", detail={"name": column.name})
    return column


def delete_column(db: Session, column_id: int, user: User) -> dict:
    column = db.get(BoardColumn, column_id)
    if column is None:
        raise HTTPException(404, "列表不存在")
    project, _member = begin_write(db, column.project_id, user)
    columns = _columns(db, project.id)
    if len(columns) <= 1:
        raise HTTPException(400, "至少保留一个列表")
    index = next(i for i, item in enumerate(columns) if item.id == column.id)
    target = columns[index - 1] if index else columns[1]
    moving = list(db.scalars(select(Card).where(Card.column_id == column.id)))
    live = _live_cards(db, target.id)
    for card in moving:
        card.column_id = target.id
    _reindex(live + [card for card in moving if not card.archived])
    name = column.name
    db.flush()
    db.delete(column)
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="column.deleted", detail={"name": name})
    db.flush()
    return _column_ids(db, project.id)


def reorder_columns(db: Session, project_id: int, user: User, ids: list[int]) -> dict:
    project, _member = begin_write(db, project_id, user)
    columns = _columns(db, project.id)
    if set(ids) != {column.id for column in columns} or len(ids) != len(columns):
        raise HTTPException(400, "列表顺序不完整")
    found = {column.id: column for column in columns}
    for index, column_id in enumerate(ids):
        found[column_id].position = index
    _touch(project)
    return {"column_ids": ids}


def _card_count(db: Session, project_id: int) -> int:
    return int(db.scalar(select(func.count()).select_from(Card).where(Card.project_id == project_id)) or 0)


def create_card(db: Session, project_id: int, user: User, column_id: int, title: str) -> Card:
    project, _member = begin_write(db, project_id, user)
    column = db.get(BoardColumn, column_id)
    if column is None or column.project_id != project.id:
        raise HTTPException(404, "列表不存在")
    if _card_count(db, project.id) >= MAX_CARDS:
        raise HTTPException(400, "卡片数量已达上限")
    card = Card(
        project_id=project.id,
        column_id=column.id,
        title=title,
        position=len(_live_cards(db, column.id)),
        created_by=user.id,
    )
    db.add(card)
    db.flush()
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="card.created", card_id=card.id, detail={"title": title})
    return card




def update_card(db: Session, card_id: int, user: User, data: dict) -> Card:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    project = _lock_project(db, project.id)
    changed = []
    if "title" in data and data["title"] != card.title:
        card.title = data["title"]
        changed.append("title")
    if "description" in data and data["description"] != card.description:
        card.description = data["description"]
        changed.append("description")
    if "priority" in data and data["priority"] != card.priority:
        card.priority = data["priority"]
        changed.append("priority")
    if "due_on" in data and data["due_on"] != card.due_on:
        card.due_on = data["due_on"]
        changed.append("due")
    if "cover_color" in data and data["cover_color"] != card.cover_color:
        card.cover_color = data["cover_color"]
        changed.append("cover")
    if "done" in data and bool(data["done"]) != bool(card.done):
        card.done = bool(data["done"])
        changed.append("done")
    if changed:
        card.updated_at = utcnow()
        _touch(project)
        _activity(db, project_id=project.id, user_id=user.id, action="card.updated", card_id=card.id, detail={"title": card.title, "fields": changed})
    return card


def move_card(db: Session, card_id: int, user: User, column_id: int, index: int) -> dict:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    if card.archived:
        raise HTTPException(409, "请先恢复卡片")
    project = _lock_project(db, project.id)
    column = db.get(BoardColumn, column_id)
    if column is None or column.project_id != project.id:
        raise HTTPException(404, "列表不存在")
    source_id = card.column_id
    source_column = db.get(BoardColumn, source_id)
    source_name = source_column.name if source_column else column.name
    before = _live_cards(db, source_id)
    old_index = next(i for i, item in enumerate(before) if item.id == card.id)
    source = [item for item in before if item.id != card.id]
    if source_id == column.id:
        target = source
    else:
        target = _live_cards(db, column.id)
        _reindex(source)
    placed = min(max(index, 0), len(target))
    target.insert(placed, card)
    card.column_id = column.id
    _reindex(target)
    card.updated_at = utcnow()
    _touch(project)
    if source_id != column.id or old_index != placed:
        _activity(
            db,
            project_id=project.id,
            user_id=user.id,
            action="card.moved",
            card_id=card.id,
            detail={"title": card.title, "from": source_name, "to": column.name},
        )
    db.flush()
    affected = {source_id, column.id}
    return {
        "columns": [
            {"id": column_id, "card_ids": [item.id for item in _live_cards(db, column_id)]}
            for column_id in affected
        ]
    }


def set_card_archived(db: Session, card_id: int, user: User, archived: bool) -> Card:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    project = _lock_project(db, project.id)
    card.archived = archived
    if not archived:
        others = [item for item in _live_cards(db, card.column_id) if item.id != card.id]
        others.append(card)
        _reindex(others)
    else:
        _reindex(_live_cards(db, card.column_id, exclude=card.id))
    card.updated_at = utcnow()
    _touch(project)
    _activity(
        db,
        project_id=project.id,
        user_id=user.id,
        action="card.archived" if archived else "card.restored",
        card_id=card.id,
        detail={"title": card.title},
    )
    return card


def delete_card(db: Session, card_id: int, user: User) -> None:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    project = _lock_project(db, project.id)
    for row in db.scalars(select(Attachment).where(Attachment.card_id == card.id)):
        defer_unlink(db, UPLOAD_DIR / row.stored_name)
    title = card.title
    column_id = card.column_id
    db.delete(card)
    db.flush()
    _reindex(_live_cards(db, column_id))
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="card.deleted", detail={"title": title})


def duplicate_card(db: Session, card_id: int, user: User) -> Card:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    project = _lock_project(db, project.id)
    if _card_count(db, project.id) >= MAX_CARDS:
        raise HTTPException(400, "卡片数量已达上限")
    title = card.title if card.title.endswith(" 副本") else f"{card.title} 副本"
    copy = Card(
        project_id=project.id,
        column_id=card.column_id,
        title=title[:180],
        description=card.description,
        priority=card.priority,
        due_on=card.due_on,
        cover_color=card.cover_color,
        created_by=user.id,
        position=card.position + 1,
    )
    db.add(copy)
    db.flush()
    for label_id in db.scalars(select(CardLabel.label_id).where(CardLabel.card_id == card.id)):
        db.add(CardLabel(card_id=copy.id, label_id=label_id))
    lists = list(db.scalars(select(Checklist).where(Checklist.card_id == card.id).order_by(Checklist.position, Checklist.id)))
    for checklist in lists:
        copied = Checklist(card_id=copy.id, title=checklist.title, position=checklist.position)
        db.add(copied)
        db.flush()
        items = db.scalars(
            select(ChecklistItem).where(ChecklistItem.checklist_id == checklist.id).order_by(ChecklistItem.position, ChecklistItem.id)
        )
        for item in items:
            db.add(ChecklistItem(checklist_id=copied.id, text=item.text, done=item.done, position=item.position))
    live = _live_cards(db, card.column_id)
    ordered = []
    for item in live:
        ordered.append(item)
        if item.id == card.id:
            ordered.append(copy)
    if copy not in ordered:
        ordered.append(copy)
    _reindex(ordered)
    _touch(project)
    _activity(db, project_id=project.id, user_id=user.id, action="card.duplicated", card_id=copy.id, detail={"title": copy.title})
    return copy


def replace_labels(db: Session, card_id: int, user: User, ids: list[int]) -> Card:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    project = _lock_project(db, project.id)
    wanted = list(dict.fromkeys(ids))
    if wanted:
        found = set(db.scalars(select(Label.id).where(Label.project_id == project.id, Label.id.in_(wanted))))
        if found != set(wanted):
            raise HTTPException(400, "包含不属于本项目的标签")
    current = list(db.scalars(select(CardLabel).where(CardLabel.card_id == card.id)))
    current_ids = {row.label_id for row in current}
    for row in current:
        if row.label_id not in wanted:
            db.delete(row)
    for label_id in wanted:
        if label_id not in current_ids:
            db.add(CardLabel(card_id=card.id, label_id=label_id))
    card.updated_at = utcnow()
    _touch(project)
    return card


def replace_assignees(db: Session, card_id: int, user: User, ids: list[int]) -> Card:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    project = _lock_project(db, project.id)
    wanted = list(dict.fromkeys(ids))
    members = _member_ids(db, project.id)
    if any(item not in members for item in wanted):
        raise HTTPException(400, "只能指派项目成员")
    current = list(db.scalars(select(CardAssignee).where(CardAssignee.card_id == card.id)))
    current_ids = {row.user_id for row in current}
    for row in current:
        if row.user_id not in wanted:
            db.delete(row)
    added = [item for item in wanted if item not in current_ids]
    for user_id in added:
        db.add(CardAssignee(card_id=card.id, user_id=user_id))
        _notify(
            db,
            recipient_id=user_id,
            actor_id=user.id,
            type="card_assigned",
            title="新的指派",
            body=f"{user.display_name} 把你加到了「{card.title}」",
            project_id=project.id,
            card_id=card.id,
        )
    card.updated_at = utcnow()
    _touch(project)
    if added or set(current_ids) - set(wanted):
        _activity(db, project_id=project.id, user_id=user.id, action="card.assigned", card_id=card.id, detail={"title": card.title})
    return card


def create_label(db: Session, project_id: int, user: User, name: str, color: str) -> Label:
    project, _member = begin_write(db, project_id, user)
    count = int(db.scalar(select(func.count()).select_from(Label).where(Label.project_id == project.id)) or 0)
    if count >= 30:
        raise HTTPException(400, "标签数量已达上限")
    label = Label(project_id=project.id, name=name, color=color)
    db.add(label)
    db.flush()
    return label


def update_label(db: Session, label_id: int, user: User, name: str | None, color: str | None) -> Label:
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(404, "标签不存在")
    begin_write(db, label.project_id, user)
    if name is not None:
        label.name = name
    if color is not None:
        label.color = color
    return label


def delete_label(db: Session, label_id: int, user: User) -> None:
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(404, "标签不存在")
    begin_write(db, label.project_id, user)
    db.delete(label)


def create_checklist(db: Session, card_id: int, user: User, title: str) -> Checklist:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    _lock_project(db, project.id)
    count = int(db.scalar(select(func.count()).select_from(Checklist).where(Checklist.card_id == card.id)) or 0)
    if count >= 20:
        raise HTTPException(400, "清单数量已达上限")
    checklist = Checklist(card_id=card.id, title=title, position=count)
    db.add(checklist)
    card.updated_at = utcnow()
    db.flush()
    return checklist


def update_checklist(db: Session, checklist_id: int, user: User, title: str) -> Checklist:
    checklist = db.get(Checklist, checklist_id)
    if checklist is None:
        raise HTTPException(404, "清单不存在")
    card, project, _member = _require_card(db, checklist.card_id, user, "member", write=True)
    _lock_project(db, project.id)
    checklist.title = title
    card.updated_at = utcnow()
    return checklist


def delete_checklist(db: Session, checklist_id: int, user: User) -> None:
    checklist = db.get(Checklist, checklist_id)
    if checklist is None:
        raise HTTPException(404, "清单不存在")
    card, project, _member = _require_card(db, checklist.card_id, user, "member", write=True)
    _lock_project(db, project.id)
    db.delete(checklist)
    card.updated_at = utcnow()


def add_item(db: Session, checklist_id: int, user: User, text: str) -> ChecklistItem:
    checklist = db.get(Checklist, checklist_id)
    if checklist is None:
        raise HTTPException(404, "清单不存在")
    card, project, _member = _require_card(db, checklist.card_id, user, "member", write=True)
    _lock_project(db, project.id)
    count = int(db.scalar(select(func.count()).select_from(ChecklistItem).where(ChecklistItem.checklist_id == checklist.id)) or 0)
    if count >= 100:
        raise HTTPException(400, "清单项已达上限")
    item = ChecklistItem(checklist_id=checklist.id, text=text, position=count)
    db.add(item)
    card.updated_at = utcnow()
    db.flush()
    return item


def update_item(db: Session, item_id: int, user: User, data: dict) -> ChecklistItem:
    item = db.get(ChecklistItem, item_id)
    if item is None:
        raise HTTPException(404, "清单项不存在")
    checklist = db.get(Checklist, item.checklist_id)
    card, project, _member = _require_card(db, checklist.card_id, user, "member", write=True)
    _lock_project(db, project.id)
    if "text" in data:
        item.text = data["text"]
    if "done" in data:
        item.done = bool(data["done"])
    if "index" in data:
        items = list(
            db.scalars(
                select(ChecklistItem).where(ChecklistItem.checklist_id == checklist.id).order_by(ChecklistItem.position, ChecklistItem.id)
            )
        )
        items = [current for current in items if current.id != item.id]
        items.insert(min(data["index"], len(items)), item)
        for index, current in enumerate(items):
            current.position = index
    card.updated_at = utcnow()
    return item


def delete_item(db: Session, item_id: int, user: User) -> None:
    item = db.get(ChecklistItem, item_id)
    if item is None:
        raise HTTPException(404, "清单项不存在")
    checklist = db.get(Checklist, item.checklist_id)
    card, project, _member = _require_card(db, checklist.card_id, user, "member", write=True)
    _lock_project(db, project.id)
    db.delete(item)
    card.updated_at = utcnow()


def add_comment(db: Session, card_id: int, user: User, body: str) -> Comment:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    _lock_project(db, project.id)
    count = int(db.scalar(select(func.count()).select_from(Comment).where(Comment.card_id == card.id)) or 0)
    if count >= 1000:
        raise HTTPException(400, "评论已达上限")
    now = utcnow()
    comment = Comment(card_id=card.id, user_id=user.id, body=body, created_at=now, updated_at=now)
    db.add(comment)
    card.updated_at = now
    _touch(project)
    members = list(db.scalars(select(User).join(ProjectMember, ProjectMember.user_id == User.id).where(ProjectMember.project_id == project.id)))
    mentions = set(mentioned_ids(body, members))
    assignees = set(db.scalars(select(CardAssignee.user_id).where(CardAssignee.card_id == card.id)))
    watchers = set(assignees)
    watchers.add(card.created_by)
    for user_id in mentions:
        _notify(
            db,
            recipient_id=user_id,
            actor_id=user.id,
            type="mention",
            title="有人提到了你",
            body=f"{user.display_name} 在「{card.title}」提到了你",
            project_id=project.id,
            card_id=card.id,
        )
    for user_id in watchers - mentions:
        _notify(
            db,
            recipient_id=user_id,
            actor_id=user.id,
            type="card_comment",
            title="新评论",
            body=f"{user.display_name} 评论了「{card.title}」",
            project_id=project.id,
            card_id=card.id,
        )
    _activity(db, project_id=project.id, user_id=user.id, action="comment.added", card_id=card.id, detail={"title": card.title})
    db.flush()
    return comment


def update_comment(db: Session, comment_id: int, user: User, body: str) -> Comment:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(404, "评论不存在")
    card, project, _member = _require_card(db, comment.card_id, user, "member", write=True)
    if comment.user_id != user.id:
        raise HTTPException(403, "只能编辑自己的评论")
    _lock_project(db, project.id)
    comment.body = body
    comment.updated_at = utcnow()
    return comment


def delete_comment(db: Session, comment_id: int, user: User) -> None:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(404, "评论不存在")
    _card, project, member = _require_card(db, comment.card_id, user, "member", write=True)
    if comment.user_id != user.id and ROLE_RANK[member.role] < ROLE_RANK["admin"]:
        raise HTTPException(403, "只能删除自己的评论")
    _lock_project(db, project.id)
    db.delete(comment)


def add_attachment(db: Session, card_id: int, user: User, filename: str, raw: bytes) -> Attachment:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "文件不能超过 8 MB")
    if not raw:
        raise HTTPException(400, "文件是空的")
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "不支持的文件类型")
    _lock_project(db, project.id)
    stored = secrets.token_hex(16) + suffix
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / stored
    path.write_bytes(raw)
    safe_name = Path(filename or "file").name.replace("\x00", "") or "file"
    row = Attachment(card_id=card.id, user_id=user.id, filename=safe_name[:255], stored_name=stored, size=len(raw))
    db.add(row)
    try:
        db.flush()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    card.updated_at = utcnow()
    _touch(project)
    return row


def delete_attachment(db: Session, attachment_id: int, user: User) -> None:
    row = db.get(Attachment, attachment_id)
    if row is None:
        raise HTTPException(404, "附件不存在")
    _card, project, member = _require_card(db, row.card_id, user, "member", write=True)
    if row.user_id != user.id and ROLE_RANK[member.role] < ROLE_RANK["admin"]:
        raise HTTPException(403, "只能删除自己上传的附件")
    _lock_project(db, project.id)
    defer_unlink(db, UPLOAD_DIR / row.stored_name)
    db.delete(row)


def attachment_file(db: Session, attachment_id: int, user: User) -> Attachment:
    row = db.get(Attachment, attachment_id)
    if row is None:
        raise HTTPException(404, "附件不存在")
    _require_card(db, row.card_id, user)
    return row


def board_dict(db: Session, project_id: int, user: User) -> dict:
    project, member = require_access(db, project_id, user)
    columns = _columns(db, project.id)
    cards = list(db.scalars(select(Card).where(Card.project_id == project.id).order_by(Card.position, Card.id)))
    card_ids = [card.id for card in cards]
    label_map: dict[int, list[int]] = defaultdict(list)
    assignee_map: dict[int, list[int]] = defaultdict(list)
    checks: dict[int, tuple[int, int]] = {}
    comments: dict[int, int] = {}
    files: dict[int, int] = {}
    if card_ids:
        for link in db.scalars(select(CardLabel).where(CardLabel.card_id.in_(card_ids))):
            label_map[link.card_id].append(link.label_id)
        for link in db.scalars(select(CardAssignee).where(CardAssignee.card_id.in_(card_ids))):
            assignee_map[link.card_id].append(link.user_id)
        check_rows = db.execute(
            select(Checklist.card_id, func.count(ChecklistItem.id), func.coalesce(func.sum(ChecklistItem.done), 0))
            .join(ChecklistItem, ChecklistItem.checklist_id == Checklist.id)
            .where(Checklist.card_id.in_(card_ids))
            .group_by(Checklist.card_id)
        )
        checks = {card_id: (int(done or 0), int(total or 0)) for card_id, total, done in check_rows}
        comments = {
            card_id: int(total)
            for card_id, total in db.execute(
                select(Comment.card_id, func.count()).where(Comment.card_id.in_(card_ids)).group_by(Comment.card_id)
            )
        }
        files = {
            card_id: int(total)
            for card_id, total in db.execute(
                select(Attachment.card_id, func.count()).where(Attachment.card_id.in_(card_ids)).group_by(Attachment.card_id)
            )
        }
    grouped: dict[int, list[dict]] = defaultdict(list)
    for card in cards:
        done, total = checks.get(card.id, (0, 0))
        grouped[card.column_id].append(_card_brief(card, label_map[card.id], assignee_map[card.id], done, total, comments.get(card.id, 0), files.get(card.id, 0)))
    labels = [
        {"id": label.id, "name": label.name, "color": label.color}
        for label in db.scalars(select(Label).where(Label.project_id == project.id).order_by(Label.id))
    ]
    return {
        "project": project_brief(project),
        "role": member.role,
        "members": _member_rows(db, project.id),
        "labels": labels,
        "columns": [
            {
                "id": column.id,
                "name": column.name,
                "color": column.color,
                "wip_limit": column.wip_limit,
                "position": column.position,
                "cards": grouped.get(column.id, []),
            }
            for column in columns
        ],
    }


def _card_brief(card: Card, label_ids: list[int], assignee_ids: list[int], done: int, total: int, comment_count: int, attachment_count: int) -> dict:
    return {
        "id": card.id,
        "column_id": card.column_id,
        "title": card.title,
        "excerpt": excerpt(card.description),
        "priority": card.priority,
        "due_on": day(card.due_on),
        "cover_color": card.cover_color,
        "done": bool(card.done),
        "archived": bool(card.archived),
        "position": card.position,
        "created_by": card.created_by,
        "updated_at": iso(card.updated_at),
        "label_ids": label_ids,
        "assignee_ids": assignee_ids,
        "checklist": {"done": done, "total": total},
        "comment_count": comment_count,
        "attachment_count": attachment_count,
    }


def card_detail(db: Session, card_id: int, user: User) -> dict:
    card, project, member = _require_card(db, card_id, user)
    label_ids = list(db.scalars(select(CardLabel.label_id).where(CardLabel.card_id == card.id)))
    assignee_ids = list(db.scalars(select(CardAssignee.user_id).where(CardAssignee.card_id == card.id)))
    lists = list(db.scalars(select(Checklist).where(Checklist.card_id == card.id).order_by(Checklist.position, Checklist.id)))
    items = list(
        db.scalars(
            select(ChecklistItem)
            .where(ChecklistItem.checklist_id.in_([item.id for item in lists] or [0]))
            .order_by(ChecklistItem.position, ChecklistItem.id)
        )
    ) if lists else []
    by_list: dict[int, list[dict]] = defaultdict(list)
    for item in items:
        by_list[item.checklist_id].append({"id": item.id, "text": item.text, "done": bool(item.done), "position": item.position})
    comments = list(db.scalars(select(Comment).where(Comment.card_id == card.id).order_by(Comment.created_at, Comment.id)))
    people = _users(db, {comment.user_id for comment in comments} | {row.user_id for row in db.scalars(select(Attachment).where(Attachment.card_id == card.id))})
    files = list(db.scalars(select(Attachment).where(Attachment.card_id == card.id).order_by(Attachment.id)))
    activity = list(
        db.scalars(select(Activity).where(Activity.card_id == card.id).order_by(Activity.id.desc()).limit(30))
    )
    actors = _users(db, {item.user_id for item in activity})
    payload = _card_brief(card, label_ids, assignee_ids, 0, 0, len(comments), len(files))
    payload["description"] = card.description or ""
    payload["project_id"] = project.id
    payload["can_edit"] = (not project.archived) and ROLE_RANK[member.role] >= ROLE_RANK["member"]
    return {
        "card": payload,
        "checklists": [
            {"id": item.id, "title": item.title, "position": item.position, "items": by_list.get(item.id, [])}
            for item in lists
        ],
        "comments": [
            {
                "id": comment.id,
                "body": comment.body,
                "created_at": iso(comment.created_at),
                "updated_at": iso(comment.updated_at),
                "edited": (comment.updated_at - comment.created_at).total_seconds() > 1,
                "mine": comment.user_id == user.id,
                "user": user_brief(people[comment.user_id]) if comment.user_id in people else None,
            }
            for comment in comments
        ],
        "attachments": [_attachment(row) for row in files],
        "activity": [_activity_item(item, actors) for item in activity],
    }


def _attachment(row: Attachment) -> dict:
    return {
        "id": row.id,
        "filename": row.filename,
        "size": row.size,
        "created_at": iso(row.created_at),
        "image": Path(row.stored_name).suffix.lower() in IMAGE_EXTENSIONS,
    }


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


def column_dict(column: BoardColumn) -> dict:
    return {"id": column.id, "name": column.name, "color": column.color, "wip_limit": column.wip_limit, "position": column.position}


def label_dict(label: Label) -> dict:
    return {"id": label.id, "name": label.name, "color": label.color}


def checklist_dict(checklist: Checklist) -> dict:
    return {"id": checklist.id, "title": checklist.title, "position": checklist.position, "items": []}


def item_dict(item: ChecklistItem) -> dict:
    return {"id": item.id, "text": item.text, "done": bool(item.done), "position": item.position}
