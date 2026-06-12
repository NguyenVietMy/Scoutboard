"""Phase 6: web UI — routes render and the brief/state/source actions work."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import select

from scoutboard.cluster.build import build_clusters
from scoutboard.db import get_session
from scoutboard.ingest.jsonl import import_jsonl
from scoutboard.models import Cluster, OpportunityBrief, Source
from scoutboard.signals.pipeline import classify
from scoutboard.web import service
from scoutboard.web.app import create_app

FIXTURES = Path(__file__).parent / "fixtures"


def _seed(session) -> int:
    import_jsonl(session, FIXTURES / "cluster_seed.jsonl")
    classify(session, use_ai=False)
    build_clusters(session)
    return session.exec(select(Cluster).order_by(Cluster.item_count.desc())).first().id


def test_inbox_and_detail_render(scoutboard_home):
    with get_session() as session:
        cid = _seed(session)
    client = TestClient(create_app())

    home = client.get("/")
    assert home.status_code == 200
    assert "Opportunity clusters" in home.text

    detail = client.get(f"/clusters/{cid}")
    assert detail.status_code == 200
    assert "Evidence review" in detail.text
    # Provenance: a real source URL is present on the page.
    assert "news.ycombinator.com" in detail.text or "github.com" in detail.text


def test_generate_brief_offline_via_post(scoutboard_home):
    with get_session() as session:
        cid = _seed(session)
    client = TestClient(create_app())

    resp = client.post(f"/clusters/{cid}/brief", data={"rules_only": "1"})
    assert resp.status_code == 200  # followed the 303 redirect to detail
    with get_session() as session:
        briefs = session.exec(
            select(OpportunityBrief).where(OpportunityBrief.cluster_id == cid)
        ).all()
        assert len(briefs) == 1


def test_set_state_and_filter(scoutboard_home):
    with get_session() as session:
        cid = _seed(session)
    client = TestClient(create_app())

    client.post(f"/clusters/{cid}/state", data={"state": "archived"})
    with get_session() as session:
        assert session.get(Cluster, cid).state == "archived"

    # Filtering by state=archived shows it; state=new should not.
    archived = client.get("/", params={"state": "archived"})
    assert str(cid) in archived.text


def test_tag_filter_matches_topic_terms(scoutboard_home):
    with get_session() as session:
        _seed(session)
        all_rows = service.list_clusters(session, service.Filters())
        tags = service.all_tags(all_rows)
        assert tags  # clusters expose topic terms as tags

        a_tag = tags[0]
        filtered = service.list_clusters(session, service.Filters(tag=a_tag))
        assert filtered
        assert all(a_tag in r.tags for r in filtered)
        # A tag that doesn't exist returns nothing.
        assert service.list_clusters(session, service.Filters(tag="zzzznope")) == []


def test_within_days_filters_by_recency(scoutboard_home):
    with get_session() as session:
        _seed(session)
        # Seed items carry no published_at -> last_seen is None -> excluded by a window.
        recent = service.list_clusters(session, service.Filters(within_days=7))
        assert recent == []
        # No window -> all clusters present.
        assert service.list_clusters(session, service.Filters()) != []


def test_digest_and_sources_pages(scoutboard_home):
    with get_session() as session:
        _seed(session)
    client = TestClient(create_app())

    assert client.get("/digest", params={"days": 3650}).status_code == 200

    sources_page = client.get("/sources")
    assert sources_page.status_code == 200

    client.post("/sources", data={"kind": "hn", "feed": "ask", "limit": 25})
    with get_session() as session:
        sources = session.exec(select(Source)).all()
        assert any(s.kind == "hn" and s.config.get("feed") == "ask" for s in sources)
