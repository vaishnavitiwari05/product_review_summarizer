"""SQLAlchemy engine/session management. SQLite by default, PostgreSQL via DATABASE_URL."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_Session: sessionmaker | None = None


def configure_engine(url: str | None = None) -> Engine:
    """(Re)create the engine. Called on app start-up; tests call it with a temp DB."""
    global _engine, _Session
    from app.utils import config
    url = url or config.settings.database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs["pool_pre_ping"] = True
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _pragmas(dbapi_conn, _):        # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine or configure_engine()


def init_db() -> None:
    from app.models.db import Base
    Base.metadata.create_all(get_engine())


def new_session() -> Session:
    get_engine()
    assert _Session is not None
    return _Session()


@contextmanager
def session_scope():
    s = new_session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db():
    """FastAPI dependency."""
    s = new_session()
    try:
        yield s
    finally:
        s.close()
