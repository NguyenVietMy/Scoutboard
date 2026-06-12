"""Phase 4: briefs & digest — structural provenance, offline path, AI body rendering."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import select

from scoutboard.briefs.digest import generate_digest
from scoutboard.briefs.evidence import gather_cluster_evidence
from scoutboard.briefs.generator import generate_brief, render_brief
from scoutboard.cluster.build import build_clusters
from scoutboard.db import get_session
from scoutboard.ingest.jsonl import import_jsonl
from scoutboard.models import Cluster, OpportunityBrief
from scoutboard.signals.pipeline import classify

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_clusters(session) -> None:
    import_jsonl(session, FIXTURES / "cluster_seed.jsonl")
    classify(session, use_ai=False)
    build_clusters(session)


def _first_cluster_id(session) -> int:
    return session.exec(select(Cluster).order_by(Cluster.item_count.desc())).first().id


def test_evidence_pack_uses_real_urls(scoutboard_home):
    with get_session() as session:
        _seed_clusters(session)
        cid = _first_cluster_id(session)
        pack = gather_cluster_evidence(session, cid)
        assert pack is not None
        assert pack.item_count == len(pack.evidence)
        # Evidence numbers are 1..n and every item carries a real source URL.
        assert [e.n for e in pack.evidence] == list(range(1, len(pack.evidence) + 1))
        assert all(e.url.startswith("http") for e in pack.evidence)
        # Exactly one representative.
        assert sum(1 for e in pack.evidence if e.representative) == 1


def test_generate_brief_offline_is_cited_and_persisted(scoutboard_home):
    with get_session() as session:
        _seed_clusters(session)
        cid = _first_cluster_id(session)
        result = generate_brief(session, cid, use_ai=False)
        assert result is not None
        _title, md = result
        assert "## Evidence" in md
        # Provenance: a real source URL appears in the rendered brief.
        pack = gather_cluster_evidence(session, cid)
        assert pack.evidence[0].url in md
        # Persisted.
        briefs = session.exec(
            select(OpportunityBrief).where(OpportunityBrief.cluster_id == cid)
        ).all()
        assert len(briefs) == 1


def test_render_brief_includes_ai_body(scoutboard_home):
    with get_session() as session:
        _seed_clusters(session)
        cid = _first_cluster_id(session)
        pack = gather_cluster_evidence(session, cid)
        md = render_brief(pack, ai_body="## Summary\nA real need exists [1].")
        assert "## Summary" in md
        assert "[1]" in md


def test_generate_digest_renders(scoutboard_home):
    with get_session() as session:
        _seed_clusters(session)
        md = generate_digest(session, days=3650)  # wide window
    assert "Scoutboard Weekly Digest" in md
    assert "Top new clusters" in md
