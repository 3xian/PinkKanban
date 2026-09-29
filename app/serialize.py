from __future__ import annotations

import json
from datetime import date, datetime

from app.models import User


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def loads(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def excerpt(text: str | None, limit: int = 140) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip() + "…"


def user_brief(user: User, *, email: bool = False) -> dict:
    data = {"id": user.id, "display_name": user.display_name, "avatar_color": user.avatar_color}
    if email:
        data["email"] = user.email
    return data


def project_brief(project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "color": project.color,
        "archived": bool(project.archived),
        "owner_id": project.owner_id,
        "updated_at": iso(project.updated_at),
        "created_at": iso(project.created_at),
    }
