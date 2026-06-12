"""Postgres config, embeddings, embedding-clustering, and semantic search.

A deterministic fake provider stands in for the real (paid, networked) embedding
backend so the whole path is testable offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import select

from scoutboard import config
from scoutboard.cluster.build import build_clusters
from scoutboard.cluster.embeddings import cosine_dense
from scoutboard.db import get_session
from scoutboard.ingest.jsonl import import_jsonl
from scoutboard.models import Cluster, ItemEmbedding
from scoutboard.semantic import EmbeddingsUnavailable, embed_items, search

FIXTURES = Path(__file__).parent / "fixtures"


class FakeProvider:
    """4-d keyword-indicator embeddings: [enrichment, alternative, ci, jenkins]."""

    model = "fake-1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            tl = t.lower()
            out.append(
                [
                    1.0 if ("clay" in tl or "enrichment" in tl) else 0.0,
                    1.0 if "alternative" in tl else 0.0,
                    1.0 if ("ci" in tl or "circleci" in tl) else 0.0,
                    1.0 if ("jenkins" in tl or "actions" in tl) else 0.0,
                ]
            )
        return out


def test_cosine_dense():
    assert cosine_dense([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_dense([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_dense([], [1]) == 0.0


def test_database_url_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOUTBOARD_HOME", str(tmp_path))
    monkeypatch.setenv("SCOUTBOARD_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    config.get_settings.cache_clear()
    try:
        assert config.get_settings().database_url == "postgresql+psycopg://u:p@localhost/db"
    finally:
        config.get_settings.cache_clear()


def test_embed_and_search(scoutboard_home):
    with get_session() as session:
        import_jsonl(session, FIXTURES / "cluster_seed.jsonl")
        result = embed_items(session, FakeProvider())
        assert result.embedded == 5
        assert len(session.exec(select(ItemEmbedding)).all()) == 5

        hits = search(session, "open-source clay enrichment alternative", FakeProvider(), k=3)
        assert hits
        # Top hit should be a Clay/enrichment item, not a CI one.
        assert "clay" in (hits[0].item.title or hits[0].item.body or "").lower() \
            or "enrichment" in (hits[0].item.body or "").lower()


def test_embed_idempotent(scoutboard_home):
    with get_session() as session:
        import_jsonl(session, FIXTURES / "cluster_seed.jsonl")
        embed_items(session, FakeProvider())
    with get_session() as session:
        again = embed_items(session, FakeProvider())
        assert again.embedded == 0
        assert again.skipped == 5


def test_embedding_clustering_groups_by_topic(scoutboard_home):
    from scoutboard.signals.pipeline import classify

    with get_session() as session:
        import_jsonl(session, FIXTURES / "cluster_seed.jsonl")
        classify(session, use_ai=False)
    with get_session() as session:
        report = build_clusters(session, use_embeddings=True, provider=FakeProvider())
        assert report.clusters >= 1
        assert report.multi_item_clusters >= 1
        # Embeddings were persisted as a side effect.
        assert len(session.exec(select(ItemEmbedding)).all()) == 5
        assert session.exec(select(Cluster)).first() is not None


def test_search_without_provider_raises(scoutboard_home):
    with get_session() as session:
        import_jsonl(session, FIXTURES / "cluster_seed.jsonl")
        with pytest.raises(EmbeddingsUnavailable):
            search(session, "anything")  # no VOYAGE_API_KEY in test env
