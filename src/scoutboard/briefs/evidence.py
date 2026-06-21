"""Assemble a cluster's evidence pack from real ``items`` rows.

This is the provenance backbone: every brief is built on numbered evidence with
real URLs and timestamps pulled from the database, so citations cannot be
hallucinated — the AI only writes prose *around* this fixed evidence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from scoutboard.models import Cluster, ClusterItem, Item, Signal


@dataclass
class EvidenceItem:
    n: int
    item_id: int
    source: str
    url: str
    title: str | None
    snippet: str
    published_at: datetime | None
    intent: str | None
    representative: bool


@dataclass
class ClusterEvidence:
    cluster: Cluster
    evidence: list[EvidenceItem] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    intents: list[tuple[str, int]] = field(default_factory=list)
    tools: list[tuple[str, int]] = field(default_factory=list)
    item_count: int = 0
    mentions_last_week: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    def as_prompt_block(self) -> str:
        """Render the numbered evidence as plain text for the AI payload."""

        lines = []
        for e in self.evidence:
            ts = e.published_at.date().isoformat() if e.published_at else "n/a"
            lines.append(f"[{e.n}] ({e.source}, {ts}) {e.snippet} — {e.url}")
        return "\n".join(lines)


def _as_aware(dt: datetime | None) -> datetime | None:
    """Treat a stored datetime as UTC. SQLite drops tzinfo on read, so naive
    values come back from the DB and can't be compared to aware ``now`` values."""

    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def gather_cluster_evidence(
    session: Session, cluster_id: int, *, now: datetime | None = None
) -> ClusterEvidence | None:
    cluster = session.get(Cluster, cluster_id)
    if cluster is None:
        return None
    now = now or datetime.now(UTC)
    week_ago = now - timedelta(days=7)

    links = session.exec(
        select(ClusterItem).where(ClusterItem.cluster_id == cluster_id)
    ).all()

    pack = ClusterEvidence(cluster=cluster, item_count=len(links))
    source_counts: Counter = Counter()
    intent_counts: Counter = Counter()
    tool_counts: Counter = Counter()

    # Representative item(s) first, then by recency.
    def sort_key(link: ClusterItem):
        item = session.get(Item, link.item_id)
        ts = item.published_at if item else None
        return (not link.representative, -(ts.timestamp() if ts else 0))

    for n, link in enumerate(sorted(links, key=sort_key), start=1):
        item = session.get(Item, link.item_id)
        if item is None:
            continue
        signal = session.exec(
            select(Signal).where(Signal.item_id == item.id)
        ).first()
        source_counts[item.source] += 1
        if signal:
            intent_counts[signal.intent] += 1
            for tool in signal.mentioned_tools:
                tool_counts[tool] += 1
        published = _as_aware(item.published_at)
        if published and published >= week_ago:
            pack.mentions_last_week += 1
        pack.evidence.append(
            EvidenceItem(
                n=n,
                item_id=item.id,
                source=item.source,
                url=item.source_url,
                title=item.title,
                snippet=(link.evidence_snippet or item.title or "")[:300],
                published_at=item.published_at,
                intent=signal.intent if signal else None,
                representative=link.representative,
            )
        )

    pack.sources = sorted(source_counts)
    pack.intents = intent_counts.most_common()
    pack.tools = tool_counts.most_common()
    pack.first_seen = cluster.first_seen_at
    pack.last_seen = cluster.latest_seen_at
    return pack
