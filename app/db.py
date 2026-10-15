from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import database_url

_engine = None
_session_factory = None
_UNLINKS = "pending_unlinks"


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(
            database_url(),
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session_factory():
    get_engine()
    return _session_factory


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def ensure_database() -> None:
    url = make_url(database_url())
    database = url.database
    if not database or "`" in database:
        raise RuntimeError("DATABASE_URL 缺少数据库名")
    probe = create_engine(url, pool_pre_ping=True)
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
        return
    except Exception as exc:
        if "1049" not in str(exc) and "Unknown database" not in str(exc):
            raise
    finally:
        probe.dispose()
    admin = create_engine(url.set(database=""), isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(
                f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        admin.dispose()


def defer_unlink(db: Session, path: Path) -> None:
    db.info.setdefault(_UNLINKS, []).append(path)


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
        paths = list(db.info.get(_UNLINKS, []))
        db.commit()
        for path in paths:
            path.unlink(missing_ok=True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app.models import Base

    ensure_database()
    engine = get_engine()
    Base.metadata.create_all(engine)
    upgrade_schema(engine)


def upgrade_schema(engine=None) -> None:
    engine = engine or get_engine()
    if engine.dialect.name != "mysql":
        return
    _ensure_card_responsible(engine)
    if _schema_has(
        engine,
        "SELECT 1 FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
        "AND COLUMN_NAME = :column AND IS_NULLABLE = 'NO'",
        {"table": "access_tokens", "column": "expires_at"},
    ):
        _alter(engine, "ALTER TABLE access_tokens MODIFY COLUMN expires_at DATETIME NULL")


def _schema_has(engine, sql: str, params: dict) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text(sql), params).scalar())


def _duplicate_schema(exc: Exception) -> bool:
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ())
    if args and args[0] in {1022, 1060, 1061, 1826}:
        return True
    message = str(orig or exc).lower()
    return "duplicate" in message


def _alter(engine, sql: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except (OperationalError, ProgrammingError) as exc:
        if _duplicate_schema(exc):
            return
        raise


def _ensure_card_responsible(engine) -> None:
    params = {"table": "cards", "column": "responsible_user_id"}
    if not _schema_has(
        engine,
        "SELECT 1 FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column",
        params,
    ):
        _alter(engine, "ALTER TABLE `cards` ADD COLUMN `responsible_user_id` INT NULL")
    if not _schema_has(
        engine,
        "SELECT 1 FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column",
        params,
    ):
        _alter(engine, "ALTER TABLE `cards` ADD INDEX `ix_cards_responsible_user_id` (`responsible_user_id`)")
    if not _schema_has(
        engine,
        "SELECT 1 FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
        "AND COLUMN_NAME = :column AND REFERENCED_TABLE_NAME IS NOT NULL",
        params,
    ):
        _alter(
            engine,
            "ALTER TABLE `cards` ADD CONSTRAINT `fk_cards_responsible_user` "
            "FOREIGN KEY (`responsible_user_id`) REFERENCES `users` (`id`)",
        )


def truncate_all() -> None:
    from app.models import Base

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS `{table.name}`")
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    Base.metadata.create_all(engine)
