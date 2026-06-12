"""Shared pytest fixtures.

Every test gets an isolated Scoutboard home (temp dir) and a fresh database so
tests never touch the user's real ``~/.scoutboard``.
"""

from __future__ import annotations

import pytest

from scoutboard import config, db


@pytest.fixture
def scoutboard_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SCOUTBOARD_HOME", str(home))
    # Drop cached settings/engine so they re-read the patched env.
    config.get_settings.cache_clear()
    db.reset_engine()
    db.init_db()
    yield home
    db.reset_engine()
    config.get_settings.cache_clear()
