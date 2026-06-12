"""Phase 1: ingestion — adapters parse fixtures, JSONL imports, dedup holds."""

from __future__ import annotations

import json
from pathlib import Path

import feedparser
from sqlmodel import func, select

from scoutboard.db import get_session
from scoutboard.ingest.github import parse_issues
from scoutboard.ingest.hackernews import parse_hits
from scoutboard.ingest.jsonl import import_jsonl
from scoutboard.ingest.normalize import store_items
from scoutboard.ingest.rss import parse_feed
from scoutboard.models import Item, RawItem

FIXTURES = Path(__file__).parent / "fixtures"


def _count(session, model) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


# --- pure parsers (no network) -------------------------------------------------


def test_parse_hn_hits():
    hits = json.loads((FIXTURES / "hn_search.json").read_text())["hits"]
    items = parse_hits(hits, "ask")
    assert len(items) == 2
    first = items[0]
    assert first.source == "hn"
    assert first.external_id == "hn:39000001"
    assert first.source_url.endswith("id=39000001")
    assert first.engagement.likes == 87
    assert "hn:ask" in first.tags


def test_parse_github_issues_filters_prs():
    issues = json.loads((FIXTURES / "github_issues.json").read_text())
    items = parse_issues(issues, "owner/name")
    # The PR (#102) is filtered out.
    assert len(items) == 1
    issue = items[0]
    assert issue.external_id == "github:owner/name#101"
    assert "enhancement" in issue.tags
    assert issue.engagement.comments == 5


def test_parse_rss_feed():
    parsed = feedparser.parse((FIXTURES / "sample_feed.xml").read_text())
    items = parse_feed(parsed, "https://example.com/feed.xml")
    assert len(items) == 2
    assert items[0].source == "rss"
    assert items[0].title == "Why we left Airtable"
    assert items[0].parent.type == "feed"


# --- persistence + dedup -------------------------------------------------------


def test_jsonl_import_and_dedup(scoutboard_home):
    path = FIXTURES / "signals.jsonl"
    with get_session() as session:
        first = import_jsonl(session, path)
    assert first.inserted == 3
    assert first.failed == 0

    # Re-import: everything is a duplicate, nothing new.
    with get_session() as session:
        second = import_jsonl(session, path)
        assert _count(session, Item) == 3
        assert _count(session, RawItem) == 3
    assert second.inserted == 0
    assert second.skipped == 3


def test_engagement_score_computed(scoutboard_home):
    with get_session() as session:
        import_jsonl(session, FIXTURES / "signals.jsonl")
        item = session.exec(
            select(Item).where(Item.external_id == "youtube:comment:1")
        ).one()
        # 120 likes + 3*12 comments + 0.01*9000 views = 120 + 36 + 90 = 246
        assert item.engagement_score == 246.0


def test_store_items_dedup_within_batch(scoutboard_home):
    hits = json.loads((FIXTURES / "hn_search.json").read_text())["hits"]
    items = parse_hits(hits, "ask")
    with get_session() as session:
        r1 = store_items(session, items)
        r2 = store_items(session, items)  # same batch again
    assert r1.inserted == 2
    assert r2.inserted == 0
    assert r2.skipped == 2
