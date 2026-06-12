"""BYO connectors + bulk dir import."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scoutboard.db import get_session
from scoutboard.ingest.base import AdapterError
from scoutboard.ingest.connectors import ConnectorAdapter, run_command
from scoutboard.ingest.jsonl import import_jsonl_dir, iter_jsonl_text, parse_line
from scoutboard.ingest.runner import build_adapter
from scoutboard.models import Source


def _emitter(tmp_path: Path) -> Path:
    """A tiny connector script that prints two normalized items as JSONL."""

    script = tmp_path / "emit.py"
    script.write_text(
        "import json\n"
        "print(json.dumps({'source':'youtube','source_url':'https://y/1',"
        "'external_id':'yt:1','title':'clay alternative',"
        "'body':'looking for an open-source clay alternative'}))\n"
        "print(json.dumps({'source':'youtube','source_url':'https://y/2',"
        "'external_id':'yt:2','title':'b','body':'x'}))\n",
        encoding="utf-8",
    )
    return script


def test_parse_line_and_text():
    item = parse_line('{"source":"x","source_url":"u","external_id":"e"}')
    assert item is not None and item.external_id == "e"
    assert parse_line("not json") is None
    pairs = list(iter_jsonl_text('{"source":"x","source_url":"u","external_id":"e"}\n\nbad\n'))
    assert len(pairs) == 2  # blank line skipped; "bad" yields (lineno, None)
    assert pairs[1][1] is None


def test_connector_adapter_fetch(tmp_path):
    command = f'"{sys.executable}" "{_emitter(tmp_path)}"'
    items = list(ConnectorAdapter("yt", command).fetch())
    assert len(items) == 2
    assert items[0].source == "youtube"
    assert items[0].external_id == "yt:1"


def test_run_command_nonzero_raises():
    with pytest.raises(AdapterError):
        run_command(f'"{sys.executable}" -c "import sys; sys.exit(3)"')


def test_import_dir_imports_all_files(scoutboard_home, tmp_path):
    d = tmp_path / "feed"
    d.mkdir()
    (d / "a.jsonl").write_text('{"source":"x","source_url":"u1","external_id":"a1"}\n')
    (d / "b.jsonl").write_text('{"source":"x","source_url":"u2","external_id":"b1"}\n')
    with get_session() as session:
        result = import_jsonl_dir(session, d)
    assert result.inserted == 2


def test_runner_builds_connector_adapter():
    adapter = build_adapter(
        Source(kind="connector", config={"name": "x", "command": "echo hi"})
    )
    assert adapter.kind == "connector"


def test_connector_via_runner_imports(scoutboard_home, tmp_path):
    command = f'"{sys.executable}" "{_emitter(tmp_path)}"'
    with get_session() as session:
        session.add(Source(kind="connector", config={"name": "yt", "command": command}))
        session.commit()
        from scoutboard.ingest.runner import run_ingest

        runs = run_ingest(session)
    assert any(r.label == "connector:yt" and r.result and r.result.inserted == 2 for r in runs)
