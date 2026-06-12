"""Phase 0: foundation — init creates the schema and is idempotent."""

from __future__ import annotations

from sqlalchemy import inspect

from scoutboard import config, db

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
