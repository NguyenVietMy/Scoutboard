"""Phase 5: export — JSON/CSV serialization preserving provenance."""

from __future__ import annotations

import json
from pathlib import Path

from scoutboard.cluster.build import build_clusters
from scoutboard.db import get_session
from scoutboard.export import export_data
from scoutboard.ingest.jsonl import import_jsonl
from scoutboard.signals.pipeline import classify

FIXTURES = Path(__file__).parent / "fixtures"


def _seed(session) -> None:
    import_jsonl(session, FIXTURES / "cluster_seed.jsonl")
    classify(session, use_ai=False)
    build_clusters(session)


def test_export_items_json_keeps_source_urls(scoutboard_home):
    with get_session() as session:
        _seed(session)
        payload = export_data(session, "items", "json")
    rows = json.loads(payload)
    assert len(rows) == 5
    assert all(r["source_url"].startswith("http") for r in rows)
    assert {"source", "external_id", "engagement_score"} <= set(rows[0])


def test_export_clusters_csv_has_header(scoutboard_home):
    with get_session() as session:
        _seed(session)
        payload = export_data(session, "clusters", "csv")
    lines = payload.strip().splitlines()
    assert lines[0].startswith("id,label,summary")
    assert len(lines) >= 2  # header + at least one cluster


def test_export_unknown_target_raises(scoutboard_home):
    with get_session() as session:
        try:
            export_data(session, "widgets", "json")
        except ValueError as exc:
            assert "widgets" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected ValueError")
