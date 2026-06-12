"""Build opportunity clusters from signals and persist them.

Re-running rebuilds the cluster set from the current signals. User-set states
(``tracking`` / ``archived``) are carried across rebuilds by remembering them per
item, so marking a cluster as noise (archived) or interesting (tracking) survives
a re-cluster. Fresh clusters are ``new`` (MVP.md §Cluster States).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, select

from scoutboard.cluster import lexical
from scoutboard.config import get_settings
from scoutboard.models import Cluster, ClusterItem, ClusterState, Item, Signal


@dataclass
class BuildReport:
    clusters: int = 0
    multi_item_clusters: int = 0
    items_clustered: int = 0


def _snapshot_states(session: Session) -> dict[int, str]:
    """item_id -> prior non-'new' cluster state, to carry across a rebuild."""

    prior: dict[int, str] = {}
    rows = session.exec(
        select(ClusterItem.item_id, Cluster.state)
        .join(Cluster, ClusterItem.cluster_id == Cluster.id)
        .where(Cluster.state != ClusterState.new.value)
    ).all()
    for item_id, state in rows:
        prior[item_id] = state
    return prior


def _clear(session: Session) -> None:
    for row in session.exec(select(ClusterItem)).all():
        session.delete(row)
    for cluster in session.exec(select(Cluster)).all():
        session.delete(cluster)
    session.commit()


def _build_docs(session: Session) -> list[lexical.ClusterDoc]:
    docs: list[lexical.ClusterDoc] = []
    signals = session.exec(select(Signal)).all()
    for signal in signals:
        item = session.get(Item, signal.item_id)
        if item is None:
            continue
        snippet = signal.problem_phrase or (item.title or (item.body or "")[:200])
        docs.append(
            lexical.build_doc(
                item_id=item.id,
                topic_terms=signal.topic_terms,
                tools=signal.mentioned_tools,
                title=item.title,
                body=item.body,
                source=item.source,
                engagement=item.engagement_score,
                snippet=snippet,
                published_at=item.published_at,
            )
        )
    return docs


def _resolve_state(member_item_ids: list[int], prior: dict[int, str]) -> str:
    """Inherit the most common prior state among members, else 'new'."""

    states = [prior[i] for i in member_item_ids if i in prior]
    if not states:
        return ClusterState.new.value
    return Counter(states).most_common(1)[0][0]


def _cluster_groups(
    session: Session,
    docs: list[lexical.ClusterDoc],
    threshold: float | None,
    use_embeddings: bool,
    provider=None,
) -> list[list[int]]:
    settings = get_settings()
    if use_embeddings:
        from scoutboard.cluster.embeddings import get_provider, normalize
        from scoutboard.semantic import embed_items, embeddings_for_items

        prov = provider or get_provider()
        if prov is not None:
            embed_items(session, prov)
            emap = embeddings_for_items(session, [d.item_id for d in docs])
            if emap and all(d.item_id in emap for d in docs):
                for d in docs:
                    vec = normalize(emap[d.item_id])
                    d.vector = {str(i): v for i, v in enumerate(vec)}
                thr = (
                    settings.embedding_similarity_threshold if threshold is None else threshold
                )
                return lexical.group_docs(docs, threshold=thr, tool_bonus=0.05)
    # Lexical fallback (default).
    thr = settings.cluster_similarity_threshold if threshold is None else threshold
    return lexical.cluster_docs(docs, threshold=thr)


def build_clusters(
    session: Session,
    threshold: float | None = None,
    *,
    use_embeddings: bool | None = None,
    provider=None,
) -> BuildReport:
    settings = get_settings()
    use_embeddings = settings.use_embeddings if use_embeddings is None else use_embeddings

    prior = _snapshot_states(session)
    _clear(session)

    docs = _build_docs(session)
    report = BuildReport()
    if not docs:
        return report

    groups = _cluster_groups(session, docs, threshold, use_embeddings, provider)
    now = datetime.now(UTC)

    for members in groups:
        terms = lexical.top_terms(docs, members)
        rep_idx = lexical.representative_index(docs, members)
        published = [docs[i].published_at for i in members if docs[i].published_at]
        sources = {docs[i].source for i in members}
        member_item_ids = [docs[i].item_id for i in members]

        cluster = Cluster(
            label=", ".join(terms[:4]) or "uncategorized",
            summary=(
                f"{len(members)} item(s) across {len(sources)} source(s) "
                f"discussing: {', '.join(terms[:6])}."
            ),
            topic_terms=terms,
            item_count=len(members),
            state=_resolve_state(member_item_ids, prior),
            first_seen_at=min(published) if published else None,
            latest_seen_at=max(published) if published else None,
            created_at=now,
            updated_at=now,
        )
        session.add(cluster)
        session.flush()  # assign cluster.id

        for i in members:
            session.add(
                ClusterItem(
                    cluster_id=cluster.id,
                    item_id=docs[i].item_id,
                    representative=(i == rep_idx),
                    evidence_snippet=docs[i].snippet,
                )
            )
        report.clusters += 1
        report.items_clustered += len(members)
        if len(members) > 1:
            report.multi_item_clusters += 1

    session.commit()
    return report
