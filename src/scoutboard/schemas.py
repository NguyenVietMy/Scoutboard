"""Normalized item schema — the contract shared by every adapter and the JSONL importer.

Mirrors MVP.md §JSONL Import Bridge / §Normalized Item Schema. Any external
scraper can feed Scoutboard by emitting one of these per JSONL line.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Engagement(BaseModel):
    likes: int | None = None
    comments: int | None = None
    views: int | None = None

    def score(self) -> float:
        """Collapse engagement into a single transparent number.

        Comments are weighted highest (a reply is a stronger signal than a like),
        views lowest. Missing fields count as zero.
        """

        likes = self.likes or 0
        comments = self.comments or 0
        views = self.views or 0
        return float(likes) + 3.0 * float(comments) + 0.01 * float(views)


class Parent(BaseModel):
    type: str | None = None
    title: str | None = None
    url: str | None = None


class NormalizedItem(BaseModel):
    source: str
    source_url: str
    external_id: str
    title: str | None = None
    body: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    engagement: Engagement = Field(default_factory=Engagement)
    parent: Parent = Field(default_factory=Parent)
    tags: list[str] = Field(default_factory=list)
    raw_payload: dict = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def text(self) -> str:
        """Title + body, for rule/classification/clustering passes."""

        return " ".join(p for p in (self.title, self.body) if p).strip()
