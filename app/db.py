from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, text
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
    Base.metadata.create_all(get_engine())


def truncate_all() -> None:
    from app.models import Base

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS `{table.name}`")
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    Base.metadata.create_all(engine)
