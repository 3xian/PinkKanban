from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = ROOT / "uploads"


def load_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "mysql+pymysql://kanban:kanban@127.0.0.1:3307/kanban?charset=utf8mb4",
    )


def secret_key() -> str:
    return os.environ.get("SECRET_KEY", "dev-only-change-me")


def timezone_name() -> str:
    return os.environ.get("APP_TIMEZONE", "Asia/Shanghai")


def daily_project_limit() -> int:
    raw = os.environ.get("DAILY_PROJECT_LIMIT", "30")
    try:
        value = int(raw)
    except ValueError:
        return 30
    return max(1, value)


def secure_cookie() -> bool:
    return os.environ.get("APP_SECURE_COOKIE", "0") == "1"
