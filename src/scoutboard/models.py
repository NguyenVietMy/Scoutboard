"""SQLModel tables for Scoutboard.

The schema mirrors MVP.md §Initial Data Model. ``raw_items`` always retains the
full source payload for traceability; ``items`` is the normalized view the rest
of the pipeline reads. Every downstream artifact (signal, cluster, brief) traces
back to ``items`` so provenance is preserved structurally.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Intent(StrEnum):
    request = "request"
    complaint = "complaint"
    comparison = "comparison"
    migration = "migration"
    integration = "integration"
    # Later buckets (kept available, not yet emitted by the MVP rules):
    pricing_pain = "pricing_pain"
    bug_friction = "bug_friction"
    buying_intent = "buying_intent"
    launch = "launch"
    recommendation = "recommendation"
    unknown = "unknown"


class ClusterState(StrEnum):
    new = "new"
    tracking = "tracking"
    archived = "archived"


class Source(SQLModel, table=True):
    """A configured ingestion source (`scoutboard source add ...`)."""

    __tablename__ = "sources"

    id: int | None = Field(default=None, primary_key=True)
    kind: str  # "hn" | "rss" | "github"
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utcnow)


class RawItem(SQLModel, table=True):
    __tablename__ = "raw_items"

    id: int | None = Field(default=None, primary_key=True)
    source: str
    external_id: str = Field(index=True)
    source_url: str
    raw_payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    fetched_at: datetime = Field(default_factory=_utcnow)


class Item(SQLModel, table=True):
    __tablename__ = "items"

    id: int | None = Field(default=None, primary_key=True)
    raw_item_id: int | None = Field(default=None, foreign_key="raw_items.id")
    source: str = Field(index=True)
    external_id: str = Field(index=True)
    source_url: str
    title: str | None = None
    body: str | None = None
    author: str | None = None
    published_at: datetime | None = Field(default=None, index=True)
    engagement_score: float = 0.0
    parent_type: str | None = None
    parent_title: str | None = None
    parent_url: str | None = None


class Signal(SQLModel, table=True):
    __tablename__ = "signals"

    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id", index=True)
    intent: str = Intent.unknown.value
    topic_terms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    mentioned_tools: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    problem_phrase: str | None = None
    confidence: float = 0.0
    # "rules" until an AI pass overwrites it with "ai".
    method: str = "rules"
    created_at: datetime = Field(default_factory=_utcnow)


class Cluster(SQLModel, table=True):
    __tablename__ = "clusters"

    id: int | None = Field(default=None, primary_key=True)
    label: str
    summary: str | None = None
    topic_terms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    item_count: int = 0
    state: str = ClusterState.new.value
    first_seen_at: datetime | None = None
    latest_seen_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ClusterItem(SQLModel, table=True):
    __tablename__ = "cluster_items"

    cluster_id: int = Field(foreign_key="clusters.id", primary_key=True)
    item_id: int = Field(foreign_key="items.id", primary_key=True)
    representative: bool = False
    evidence_snippet: str | None = None


class OpportunityBrief(SQLModel, table=True):
    __tablename__ = "opportunity_briefs"

    id: int | None = Field(default=None, primary_key=True)
    cluster_id: int = Field(foreign_key="clusters.id", index=True)
    title: str
    markdown: str
    created_at: datetime = Field(default_factory=_utcnow)


class ItemEmbedding(SQLModel, table=True):
    """A dense embedding for an item, for optional semantic search/clustering.

    Stored as a JSON list of floats so it is portable across SQLite and Postgres
    without requiring pgvector; similarity is computed in Python at MVP scale.
    """

    __tablename__ = "item_embeddings"

    item_id: int = Field(foreign_key="items.id", primary_key=True)
    model: str
    vector: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
