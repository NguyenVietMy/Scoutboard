"""Read/query helpers for the web UI — cluster inbox filters and sorts.

Transparent signals only (frequency, recency, evidence count, source diversity);
no opaque scoring (MVP.md §Cluster Sorts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from scoutboard.briefs.evidence import ClusterEvidence, gather_cluster_evidence
from scoutboard.models import Cluster, OpportunityBrief

SORTS = {
    "recent": "Newest activity",
    "growing": "Fastest growing",
    "evidence": "Most evidence",
    "diversity": "Highest source diversity",
}


@dataclass
class ClusterRow:
    id: int
    label: str
    summary: str | None
    item_count: int
    sources: list[str]
    intents: list[tuple[str, int]]
    dominant_intent: str | None
    tools: list[str]
    recent: int
    state: str
    has_brief: bool
    last_seen: datetime | None
    tags: list[str] = field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len(self.sources)


@dataclass
class Filters:
    source: str | None = None
    intent: str | None = None
    state: str | None = None
    tool: str | None = None
    tag: str | None = None
    min_count: int = 1
    within_days: int | None = None  # only clusters active in the last N days
    has_brief: str | None = None  # "yes" | "no" | None
    sort: str = "recent"

    extra: dict = field(default_factory=dict)


def _row(cluster: Cluster, pack: ClusterEvidence, has_brief: bool) -> ClusterRow:
    return ClusterRow(
        id=cluster.id,
        label=cluster.label,
        summary=cluster.summary,
        item_count=cluster.item_count,
        sources=pack.sources,
        intents=pack.intents,
        dominant_intent=pack.intents[0][0] if pack.intents else None,
        tools=[t for t, _ in pack.tools],
        recent=pack.mentions_last_week,
        state=cluster.state,
        has_brief=has_brief,
        last_seen=cluster.latest_seen_at,
        tags=list(cluster.topic_terms),
    )


def list_clusters(session: Session, filters: Filters) -> list[ClusterRow]:
    now = datetime.now(UTC)
    brief_ids = set(session.exec(select(OpportunityBrief.cluster_id)).all())
    rows: list[ClusterRow] = []
    for cluster in session.exec(select(Cluster)).all():
        pack = gather_cluster_evidence(session, cluster.id, now=now)
        if pack is None:
            continue
        rows.append(_row(cluster, pack, cluster.id in brief_ids))

    cutoff = (
        now - timedelta(days=filters.within_days) if filters.within_days else None
    )
    rows = [r for r in rows if _matches(r, filters, cutoff)]
    return _sort(rows, filters.sort)


def _matches(row: ClusterRow, f: Filters, cutoff: datetime | None) -> bool:
    if f.source and f.source not in row.sources:
        return False
    if f.intent and f.intent not in {i for i, _ in row.intents}:
        return False
    if f.state and row.state != f.state:
        return False
    if f.tool and f.tool.lower() not in {t.lower() for t in row.tools}:
        return False
    if f.tag and f.tag.lower() not in {t.lower() for t in row.tags}:
        return False
    if row.item_count < f.min_count:
        return False
    if cutoff is not None and (row.last_seen is None or row.last_seen < cutoff):
        return False
    if f.has_brief == "yes" and not row.has_brief:
        return False
    if f.has_brief == "no" and row.has_brief:
        return False
    return True


def _sort(rows: list[ClusterRow], sort: str) -> list[ClusterRow]:
    if sort == "growing":
        return sorted(rows, key=lambda r: r.recent, reverse=True)
    if sort == "evidence":
        return sorted(rows, key=lambda r: r.item_count, reverse=True)
    if sort == "diversity":
        return sorted(rows, key=lambda r: r.source_count, reverse=True)
    # "recent" (default): newest activity, falling back to id for stability.
    return sorted(
        rows,
        key=lambda r: (r.last_seen.timestamp() if r.last_seen else 0, r.id),
        reverse=True,
    )


def all_sources(rows: list[ClusterRow]) -> list[str]:
    return sorted({s for r in rows for s in r.sources})


def all_intents(rows: list[ClusterRow]) -> list[str]:
    return sorted({i for r in rows for i, _ in r.intents})


def all_tags(rows: list[ClusterRow]) -> list[str]:
    return sorted({t for r in rows for t in r.tags})


def latest_brief(session: Session, cluster_id: int) -> OpportunityBrief | None:
    return session.exec(
        select(OpportunityBrief)
        .where(OpportunityBrief.cluster_id == cluster_id)
        .order_by(OpportunityBrief.created_at.desc())
    ).first()
