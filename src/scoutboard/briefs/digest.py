"""Weekly digest (MVP.md §Weekly Digest).

Summarizes the most interesting new or changed clusters using transparent signals
(item count, recent mentions, dominant intent) — no opaque scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlmodel import Session, select

from scoutboard.briefs.evidence import gather_cluster_evidence
from scoutboard.briefs.generator import _env
from scoutboard.models import Cluster, ClusterState, Intent, OpportunityBrief


@dataclass
class _ClusterView:
    id: int
    label: str
    summary: str | None
    item_count: int
    sources: int
    recent: int
    dominant_intent: str | None
    tools: str
    has_brief: bool


@dataclass
class _Sections:
    top_new: list[_ClusterView] = field(default_factory=list)
    growing: list[_ClusterView] = field(default_factory=list)
    complaints: list[_ClusterView] = field(default_factory=list)
    migrations: list[_ClusterView] = field(default_factory=list)


def _views(session: Session, now: datetime) -> list[tuple[Cluster, _ClusterView]]:
    brief_cluster_ids = set(session.exec(select(OpportunityBrief.cluster_id)).all())
    out: list[tuple[Cluster, _ClusterView]] = []
    for cluster in session.exec(select(Cluster)).all():
        pack = gather_cluster_evidence(session, cluster.id, now=now)
        if pack is None:
            continue
        out.append(
            (
                cluster,
                _ClusterView(
                    id=cluster.id,
                    label=cluster.label,
                    summary=cluster.summary,
                    item_count=cluster.item_count,
                    sources=len(pack.sources),
                    recent=pack.mentions_last_week,
                    dominant_intent=pack.intents[0][0] if pack.intents else None,
                    tools=", ".join(t for t, _ in pack.tools),
                    has_brief=cluster.id in brief_cluster_ids,
                ),
            )
        )
    return out


def generate_digest(session: Session, days: int = 7) -> str:
    now = datetime.now(UTC)
    views = _views(session, now)

    # Skip archived clusters from the digest workflow (MVP: hidden from main flow).
    active = [(c, v) for c, v in views if c.state != ClusterState.archived.value]

    sections = _Sections()
    sections.top_new = [
        v for c, v in sorted(active, key=lambda cv: cv[1].item_count, reverse=True)
        if c.state == ClusterState.new.value
    ][:5]
    sections.growing = [
        v for _c, v in sorted(active, key=lambda cv: cv[1].recent, reverse=True)
        if v.recent > 0
    ][:5]
    sections.complaints = [
        v for _c, v in active if v.dominant_intent == Intent.complaint.value
    ][:5]
    sections.migrations = [
        v for _c, v in active if v.dominant_intent == Intent.migration.value
    ][:5]

    return _env().get_template("digest.md.j2").render(
        generated_at=now, days=days, sections=sections
    )
