"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from scoutboard import models  # noqa: F401  (ensures tables are registered)
from scoutboard.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        settings.ensure_home()
        _engine = create_engine(settings.database_url, echo=False)
    return _engine


def init_db() -> None:
    """Create the data directory and all tables (idempotent)."""

    SQLModel.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def reset_engine() -> None:
    """Drop the cached engine (used by tests that switch data dirs)."""

    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
