"""Phase 0: foundation — init creates the schema and is idempotent."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlmodel import select

from scoutboard import config, db
from scoutboard.cli import _STARTER_SOURCES, quickstart
from scoutboard.models import Source

EXPECTED_TABLES = {
    "sources",
    "raw_items",
    "items",
    "signals",
    "clusters",
    "cluster_items",
    "opportunity_briefs",
}


def test_init_creates_all_tables(scoutboard_home):
    tables = set(inspect(db.get_engine()).get_table_names())
    assert EXPECTED_TABLES <= tables


def test_init_is_idempotent(scoutboard_home):
    # Running init again must not raise or wipe data.
    db.init_db()
    db.init_db()
    tables = set(inspect(db.get_engine()).get_table_names())
    assert EXPECTED_TABLES <= tables


def test_db_path_under_home(scoutboard_home):
    settings = config.get_settings()
    assert settings.db_path.parent == settings.home
    assert settings.db_path.exists()


def test_quickstart_seeds_sources_and_is_idempotent(scoutboard_home):
    quickstart()
    with db.get_session() as session:
        first = session.exec(select(Source)).all()
    assert len(first) == len(_STARTER_SOURCES)

    # Re-running must not duplicate the starter sources.
    quickstart()
    with db.get_session() as session:
        again = session.exec(select(Source)).all()
    assert len(again) == len(_STARTER_SOURCES)
