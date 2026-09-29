from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import ASSIGNABLE_ROLES, ROLE_RANK
from app.models import (
    CardAssignee,
    Card,
    Notification,
    Project,
    ProjectMember,
    User,
    utcnow,
)
from app.serialize import iso, loads, user_brief
from app.services.base import (
    ROLE_LABEL,
    _activity,
    _lock_project,
    _notify,
    _touch,
    begin_write,
    require_access,
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
    project, _member = begin_write(db, project_id, user, "admin")
    note = db.scalar(select(Notification).where(Notification.id == note_id).with_for_update())
    if note is None or note.project_id != project.id or note.type != "project_invite":
        raise HTTPException(404, "邀请不存在")
    if note.status != "pending":
        raise HTTPException(409, "这条邀请已经处理过了")
    if note.actor_id != user.id:
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
