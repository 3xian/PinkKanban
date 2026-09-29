from __future__ import annotations

from collections import defaultdict
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import COLORS, MAX_COLUMNS, MAX_LABELS
from app.models import (
    Attachment,
    BoardColumn,
    Card,
    CardAssignee,
    CardLabel,
    Checklist,
    ChecklistItem,
    Comment,
    Label,
    User,
    utcnow,
)
from app.serialize import iso, project_brief, user_brief
from app.services.base import (
    _activity,
    _column_ids,
    _columns,
    _live_cards,
    _reindex,
    _touch,
    begin_write,
    require_access,
)
from app.services.members import _member_rows
from app.services.cards import _card_brief


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


def create_label(db: Session, project_id: int, user: User, name: str, color: str) -> Label:
    project, _member = begin_write(db, project_id, user)
    count = int(db.scalar(select(func.count()).select_from(Label).where(Label.project_id == project.id)) or 0)
    if count >= MAX_LABELS:
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


def column_dict(column: BoardColumn) -> dict:
    return {"id": column.id, "name": column.name, "color": column.color, "wip_limit": column.wip_limit, "position": column.position}


def label_dict(label: Label) -> dict:
    return {"id": label.id, "name": label.name, "color": label.color}
