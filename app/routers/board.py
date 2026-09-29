from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.db import get_db
from app.deps import current_user
from app.models import User
from app.schemas import (
    CardIn,
    CardPatch,
    ChecklistIn,
    ColumnIn,
    ColumnPatch,
    CommentIn,
    IdsIn,
    ItemIn,
    ItemPatch,
    LabelIn,
    MoveIn,
    ReorderIn,
)
from app.services import (
    IMAGE_EXTENSIONS,
    add_attachment,
    add_comment,
    add_item,
    attachment_file,
    board_dict,
    card_detail,
    column_dict,
    create_card,
    create_checklist,
    create_column,
    create_label,
    delete_attachment,
    delete_card,
    delete_checklist,
    delete_column,
    delete_comment,
    delete_item,
    delete_label,
    duplicate_card,
    item_dict,
    label_dict,
    move_card,
    reorder_columns,
    replace_assignees,
    replace_labels,
    set_card_archived,
    update_card,
    update_checklist,
    update_column,
    update_comment,
    update_item,
    update_label,
    checklist_dict,
    _attachment,
)

router = APIRouter(prefix="/api", tags=["board"])


@router.get("/projects/{project_id}/board")
def board(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return board_dict(db, project_id, user)


@router.post("/projects/{project_id}/columns")
def add_column(project_id: int, body: ColumnIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    column = create_column(db, project_id, user, body.name, body.color, body.wip_limit)
    return column_dict(column)


@router.patch("/columns/{column_id}")
def patch_column(column_id: int, body: ColumnPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    column = update_column(db, column_id, user, body.model_dump(exclude_unset=True))
    return column_dict(column)


@router.delete("/columns/{column_id}")
def remove_column(column_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return delete_column(db, column_id, user)


@router.post("/projects/{project_id}/columns/reorder")
def order_columns(project_id: int, body: ReorderIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return reorder_columns(db, project_id, user, body.ids)


@router.post("/projects/{project_id}/cards")
def add_card(project_id: int, body: CardIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    card = create_card(db, project_id, user, body.column_id, body.title)
    return card_detail(db, card.id, user)["card"]


@router.get("/cards/{card_id}")
def read_card(card_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return card_detail(db, card_id, user)


@router.patch("/cards/{card_id}")
def patch_card(card_id: int, body: CardPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    update_card(db, card_id, user, body.model_dump(exclude_unset=True))
    return card_detail(db, card_id, user)


@router.post("/cards/{card_id}/move")
def move(card_id: int, body: MoveIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return move_card(db, card_id, user, body.column_id, body.index)


@router.post("/cards/{card_id}/archive")
def archive_card(card_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    set_card_archived(db, card_id, user, True)
    return {"ok": True}


@router.post("/cards/{card_id}/restore")
def restore_card(card_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    set_card_archived(db, card_id, user, False)
    return card_detail(db, card_id, user)


@router.delete("/cards/{card_id}")
def remove_card(card_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    delete_card(db, card_id, user)
    return {"ok": True}


@router.post("/cards/{card_id}/duplicate")
def copy_card(card_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    card = duplicate_card(db, card_id, user)
    return card_detail(db, card.id, user)["card"]


@router.post("/projects/{project_id}/labels")
def add_label(project_id: int, body: LabelIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return label_dict(create_label(db, project_id, user, body.name, body.color))


@router.patch("/labels/{label_id}")
def patch_label(label_id: int, body: LabelIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return label_dict(update_label(db, label_id, user, body.name, body.color))


@router.delete("/labels/{label_id}")
def remove_label(label_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    delete_label(db, label_id, user)
    return {"ok": True}


@router.put("/cards/{card_id}/labels")
def labels(card_id: int, body: IdsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    replace_labels(db, card_id, user, body.ids)
    return card_detail(db, card_id, user)


@router.put("/cards/{card_id}/assignees")
def assignees(card_id: int, body: IdsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    replace_assignees(db, card_id, user, body.ids)
    return card_detail(db, card_id, user)


@router.post("/cards/{card_id}/checklists")
def add_list(card_id: int, body: ChecklistIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return checklist_dict(create_checklist(db, card_id, user, body.title))


@router.patch("/checklists/{checklist_id}")
def patch_list(checklist_id: int, body: ChecklistIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return checklist_dict(update_checklist(db, checklist_id, user, body.title))


@router.delete("/checklists/{checklist_id}")
def remove_list(checklist_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    delete_checklist(db, checklist_id, user)
    return {"ok": True}


@router.post("/checklists/{checklist_id}/items")
def add_check_item(checklist_id: int, body: ItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return item_dict(add_item(db, checklist_id, user, body.text))


@router.patch("/checklist-items/{item_id}")
def patch_check_item(item_id: int, body: ItemPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return item_dict(update_item(db, item_id, user, body.model_dump(exclude_unset=True)))


@router.delete("/checklist-items/{item_id}")
def remove_check_item(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    delete_item(db, item_id, user)
    return {"ok": True}


@router.post("/cards/{card_id}/comments")
def comment(card_id: int, body: CommentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    add_comment(db, card_id, user, body.body)
    return card_detail(db, card_id, user)


@router.patch("/comments/{comment_id}")
def patch_comment(comment_id: int, body: CommentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = update_comment(db, comment_id, user, body.body)
    return card_detail(db, row.card_id, user)


@router.delete("/comments/{comment_id}")
def remove_comment(comment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    delete_comment(db, comment_id, user)
    return {"ok": True}


@router.post("/cards/{card_id}/attachments")
def upload(card_id: int, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    raw = file.file.read()
    row = add_attachment(db, card_id, user, file.filename or "", raw)
    return _attachment(row)


@router.delete("/attachments/{attachment_id}")
def remove_file(attachment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    delete_attachment(db, attachment_id, user)
    return {"ok": True}


@router.get("/attachments/{attachment_id}/file")
def download(attachment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = attachment_file(db, attachment_id, user)
    path = (UPLOAD_DIR / row.stored_name).resolve()
    root = UPLOAD_DIR.resolve()
    if not path.is_file() or not path.is_relative_to(root):
        raise HTTPException(404, "文件不存在")
    media = mimetypes.guess_type(row.stored_name)[0] or "application/octet-stream"
    inline = Path(row.stored_name).suffix.lower() in IMAGE_EXTENSIONS
    return FileResponse(path, media_type=media, filename=row.filename, content_disposition_type="inline" if inline else "attachment")
