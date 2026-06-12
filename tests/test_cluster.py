"""Phase 3: clustering — lexical grouping and persisted clusters with state carryover."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import select

from scoutboard.cluster import lexical
from scoutboard.cluster.build import build_clusters
from scoutboard.db import get_session
from scoutboard.ingest.jsonl import import_jsonl
from scoutboard.models import Cluster, ClusterItem, ClusterState
from scoutboard.signals.pipeline import classify

FIXTURES = Path(__file__).parent / "fixtures"


def _doc(item_id: int, text: str, tools: list[str]) -> lexical.ClusterDoc:
    return lexical.build_doc(
        item_id=item_id,
        topic_terms=[],
        tools=tools,
        title=None,
        body=text,
        source="test",
        engagement=float(item_id),
        snippet=text[:80],
    )


# --- pure lexical clustering ---------------------------------------------------


def test_cluster_docs_groups_similar_separates_dissimilar():
    docs = [
        _doc(1, "open-source clay alternative for lead enrichment", ["clay"]),
        _doc(2, "clay is too expensive, cheaper enrichment tool needed", ["clay"]),
        _doc(3, "kubernetes pod autoscaling and node draining", []),
    ]
    groups = lexical.cluster_docs(docs, threshold=0.18)
    # items 0 and 1 share clay/enrichment; item 2 is unrelated.
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]
    pair = next(g for g in groups if len(g) == 2)
    assert {docs[i].item_id for i in pair} == {1, 2}


# --- end-to-end build ----------------------------------------------------------


def _seed(session) -> None:
    import_jsonl(session, FIXTURES / "cluster_seed.jsonl")
    classify(session, use_ai=False)


def test_build_clusters_persists_clusters_and_items(scoutboard_home):
    with get_session() as session:
        _seed(session)
    with get_session() as session:
        report = build_clusters(session)
        assert report.clusters >= 1
        assert report.multi_item_clusters >= 1

        clusters = session.exec(select(Cluster)).all()
        # Every cluster has exactly one representative item.
        for c in clusters:
            members = session.exec(
                select(ClusterItem).where(ClusterItem.cluster_id == c.id)
            ).all()
            assert c.item_count == len(members)
            assert sum(1 for m in members if m.representative) == 1
            assert all(m.evidence_snippet for m in members)


def test_cluster_state_carries_across_rebuild(scoutboard_home):
    with get_session() as session:
        _seed(session)
    with get_session() as session:
        build_clusters(session)

    # Archive the largest cluster, then rebuild.
    with get_session() as session:
        biggest = session.exec(
            select(Cluster).order_by(Cluster.item_count.desc())
        ).first()
        archived_items = {
            ci.item_id
            for ci in session.exec(
                select(ClusterItem).where(ClusterItem.cluster_id == biggest.id)
            ).all()
        }
        biggest.state = ClusterState.archived.value
        session.add(biggest)
        session.commit()

    with get_session() as session:
        build_clusters(session)
        # The cluster containing those items should still be archived.
        rebuilt = session.exec(
            select(Cluster)
            .join(ClusterItem, ClusterItem.cluster_id == Cluster.id)
            .where(ClusterItem.item_id == next(iter(archived_items)))
        ).first()
        assert rebuilt.state == ClusterState.archived.value
