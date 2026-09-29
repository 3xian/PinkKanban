from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.constants import (
    ALLOWED_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MAX_CARDS,
    MAX_CHECKLIST_ITEMS,
    MAX_CHECKLISTS,
    MAX_COMMENTS,
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
    ProjectMember,
    User,
    utcnow,
)
from app.serialize import day, excerpt, iso, user_brief
from app.services.base import (
    _activity,
    _live_cards,
    _lock_project,
    _member_ids,
    _notify,
    _reindex,
    _touch,
    _users,
    begin_write,
    mentioned_ids,
    require_access,
    _require_card,
)
from app.services.projects import _activity_item

CARD_FIELDS = (
    ("title", "title"),
    ("description", "description"),
    ("priority", "priority"),
    ("due_on", "due"),
    ("cover_color", "cover"),
    ("done", "done"),
)


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
    for field, label in CARD_FIELDS:
        if field not in data or data[field] == getattr(card, field):
            continue
        setattr(card, field, data[field])
        changed.append(label)
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
    live.insert(next(i for i, item in enumerate(live) if item.id == card.id) + 1, copy)
    _reindex(live)
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


def _checklist_progress(by_list: dict[int, list[dict]]) -> tuple[int, int]:
    done = sum(1 for items in by_list.values() for item in items if item["done"])
    return done, sum(len(items) for items in by_list.values())


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
    payload = _card_brief(card, label_ids, assignee_ids, *_checklist_progress(by_list), len(comments), len(files))
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
        "attachments": [attachment_dict(row) for row in files],
        "activity": [_activity_item(item, actors) for item in activity],
    }


def attachment_dict(row: Attachment) -> dict:
    return {
        "id": row.id,
        "filename": row.filename,
        "size": row.size,
        "created_at": iso(row.created_at),
        "image": Path(row.stored_name).suffix.lower() in IMAGE_EXTENSIONS,
    }


def create_checklist(db: Session, card_id: int, user: User, title: str) -> Checklist:
    card, project, _member = _require_card(db, card_id, user, "member", write=True)
    _lock_project(db, project.id)
    count = int(db.scalar(select(func.count()).select_from(Checklist).where(Checklist.card_id == card.id)) or 0)
    if count >= MAX_CHECKLISTS:
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
    if count >= MAX_CHECKLIST_ITEMS:
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
    if count >= MAX_COMMENTS:
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


def checklist_dict(checklist: Checklist) -> dict:
    return {"id": checklist.id, "title": checklist.title, "position": checklist.position, "items": []}


def item_dict(item: ChecklistItem) -> dict:
    return {"id": item.id, "text": item.text, "done": bool(item.done), "position": item.position}
