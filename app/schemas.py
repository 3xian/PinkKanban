from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.constants import ASSIGNABLE_ROLES, COLORS, PRIORITIES

EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}")
NAME_RE = re.compile(r"^[^\x00-\x1f]{1,32}$")


def clean_email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL_RE.fullmatch(email) or len(email) > 254:
        raise ValueError("请输入有效的邮箱")
    return email


def clean_name(value: str, *, limit: int, empty: str) -> str:
    text = " ".join(value.strip().split())
    if not text:
        raise ValueError(empty)
    if len(text) > limit or any(ord(ch) < 32 for ch in text):
        raise ValueError(f"不能超过 {limit} 个字")
    return text


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    display_name: str
    code: str = ""

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str) -> str:
        text = clean_name(value, limit=32, empty="请填写显示名")
        if not NAME_RE.fullmatch(text):
            raise ValueError("显示名包含无法使用的字符")
        return text

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        text = "".join(value.split())
        if not re.fullmatch(r"\d{6}", text):
            raise ValueError("请输入 6 位验证码")
        return text


class EmailIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return clean_email(value)


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return clean_email(value)


class ProfileIn(BaseModel):
    display_name: str | None = None
    avatar_color: str | None = None

    @field_validator("display_name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_name(value, limit=32, empty="请填写显示名")

    @field_validator("avatar_color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in COLORS:
            raise ValueError("不支持的颜色")
        return value


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    color: str = COLORS[0]

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_name(value, limit=60, empty="请填写项目名称")

    @field_validator("description")
    @classmethod
    def _desc(cls, value: str) -> str:
        text = value.strip()
        if len(text) > 2000:
            raise ValueError("简介不能超过 2000 个字")
        return text

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        if value not in COLORS:
            raise ValueError("不支持的颜色")
        return value


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_name(value, limit=60, empty="请填写项目名称")

    @field_validator("description")
    @classmethod
    def _desc(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if len(text) > 2000:
            raise ValueError("简介不能超过 2000 个字")
        return text

    @field_validator("color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in COLORS:
            raise ValueError("不支持的颜色")
        return value


class InviteIn(BaseModel):
    email: str
    role: str = "member"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in ASSIGNABLE_ROLES:
            raise ValueError("角色只能是管理员、成员或只读")
        return value


class RoleIn(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in ASSIGNABLE_ROLES:
            raise ValueError("角色只能是管理员、成员或只读")
        return value


class TransferIn(BaseModel):
    user_id: int


class ColumnIn(BaseModel):
    name: str
    color: str = COLORS[6]
    wip_limit: int | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_name(value, limit=40, empty="请填写列表名称")

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        if value not in COLORS:
            raise ValueError("不支持的颜色")
        return value

    @field_validator("wip_limit")
    @classmethod
    def _wip(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1 or value > 99:
            raise ValueError("在制品上限需在 1 到 99 之间")
        return value


class ColumnPatch(BaseModel):
    name: str | None = None
    color: str | None = None
    wip_limit: int | None = None
    clear_wip: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_name(value, limit=40, empty="请填写列表名称")

    @field_validator("color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in COLORS:
            raise ValueError("不支持的颜色")
        return value

    @field_validator("wip_limit")
    @classmethod
    def _wip(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1 or value > 99:
            raise ValueError("在制品上限需在 1 到 99 之间")
        return value


class ReorderIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class CardIn(BaseModel):
    column_id: int
    title: str

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return clean_name(value, limit=180, empty="请填写卡片标题")


class CardPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    due_on: date | None = None
    cover_color: str | None = None
    done: bool | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_name(value, limit=180, empty="请填写卡片标题")

    @field_validator("description")
    @classmethod
    def _desc(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > 20000:
            raise ValueError("描述过长")
        return value.replace("\r\n", "\n")

    @field_validator("priority")
    @classmethod
    def _priority(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in PRIORITIES:
            raise ValueError("不支持的优先级")
        return value

    @field_validator("cover_color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in COLORS:
            raise ValueError("不支持的颜色")
        return value


class MoveIn(BaseModel):
    column_id: int
    index: int = Field(ge=0)


class IdsIn(BaseModel):
    ids: list[int]


class LabelIn(BaseModel):
    name: str
    color: str = COLORS[0]

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_name(value, limit=24, empty="请填写标签名")

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        if value not in COLORS:
            raise ValueError("不支持的颜色")
        return value


class ChecklistIn(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return clean_name(value, limit=80, empty="请填写清单标题")


class ItemIn(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return clean_name(value, limit=200, empty="请填写清单项")


class ItemPatch(BaseModel):
    text: str | None = None
    done: bool | None = None
    index: int | None = Field(default=None, ge=0)

    @field_validator("text")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_name(value, limit=200, empty="请填写清单项")


class CommentIn(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        text = value.replace("\r\n", "\n").strip()
        if not text:
            raise ValueError("评论不能为空")
        if len(text) > 4000:
            raise ValueError("评论不能超过 4000 个字")
        return text
