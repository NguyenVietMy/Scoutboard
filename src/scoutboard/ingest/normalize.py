"""Persist NormalizedItems into raw_items + items, deduplicating on (source, external_id).

This is the single idempotency boundary for all ingestion. Re-running ingest or
re-importing the same JSONL never creates duplicate items.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import Session, select

from scoutboard.models import Item, RawItem
from scoutboard.schemas import NormalizedItem


@dataclass
class IngestResult:
    inserted: int = 0
    skipped: int = 0  # already present (dedup)
    failed: int = 0   # invalid rows

    def merge(self, other: IngestResult) -> None:
        self.inserted += other.inserted
        self.skipped += other.skipped
        self.failed += other.failed


def _exists(session: Session, source: str, external_id: str) -> bool:
    stmt = select(Item.id).where(Item.source == source, Item.external_id == external_id)
    return session.exec(stmt).first() is not None


def store_item(session: Session, item: NormalizedItem) -> bool:
    """Insert one normalized item. Returns False if it was a duplicate.

    The full payload is preserved in ``raw_items`` for traceability; ``items``
    holds the normalized view the pipeline reads.
    """

    if _exists(session, item.source, item.external_id):
        return False

    raw = RawItem(
        source=item.source,
        external_id=item.external_id,
        source_url=item.source_url,
        raw_payload=item.raw_payload or item.model_dump(mode="json"),
        fetched_at=item.fetched_at,
    )
    session.add(raw)
    session.flush()  # assign raw.id

    session.add(
        Item(
            raw_item_id=raw.id,
            source=item.source,
            external_id=item.external_id,
            source_url=item.source_url,
            title=item.title,
            body=item.body,
            author=item.author,
            published_at=item.published_at,
            engagement_score=item.engagement.score(),
            parent_type=item.parent.type,
            parent_title=item.parent.title,
            parent_url=item.parent.url,
        )
    )
    return True


def store_items(session: Session, items: Iterable[NormalizedItem]) -> IngestResult:
    result = IngestResult()
    for item in items:
        try:
            if store_item(session, item):
                result.inserted += 1
            else:
                result.skipped += 1
        except Exception:
            result.failed += 1
    session.commit()
    return result
