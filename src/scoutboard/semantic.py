"""Item embeddings and semantic search (optional, opt-in).

Embeddings are stored per item as JSON float lists, so similarity search works on
both SQLite and Postgres without pgvector — cosine is computed in Python, which is
fine at MVP scale. For large corpora on Postgres, swap in pgvector later; the
storage shape is already a vector.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from scoutboard.cluster.embeddings import EmbeddingProvider, cosine_dense, get_provider
from scoutboard.models import Item, ItemEmbedding


class EmbeddingsUnavailable(RuntimeError):
    """Raised when an embedding op is attempted with no provider configured."""


def item_text(item: Item) -> str:
    return " ".join(p for p in (item.title, item.body) if p).strip()


@dataclass
class EmbedResult:
    embedded: int = 0
    skipped: int = 0  # already embedded with the current model


@dataclass
class SearchHit:
    item: Item
    score: float


def _resolve(provider: EmbeddingProvider | None) -> EmbeddingProvider:
    provider = provider or get_provider()
    if provider is None:
        raise EmbeddingsUnavailable(
            "No embedding provider configured. Set VOYAGE_API_KEY to enable embeddings."
        )
    return provider


def embed_items(session: Session, provider: EmbeddingProvider | None = None) -> EmbedResult:
    """Embed items that lack an up-to-date embedding for the active model."""

    provider = _resolve(provider)
    existing = {
        e.item_id: e
        for e in session.exec(select(ItemEmbedding)).all()
    }
    pending = [
        item
        for item in session.exec(select(Item)).all()
        if item.id not in existing or existing[item.id].model != provider.model
    ]
    result = EmbedResult(skipped=len(existing))
    if not pending:
        return result

    vectors = provider.embed([item_text(item) for item in pending])
    for item, vector in zip(pending, vectors, strict=False):
        row = existing.get(item.id)
        if row is None:
            session.add(ItemEmbedding(item_id=item.id, model=provider.model, vector=vector))
        else:
            row.model = provider.model
            row.vector = vector
            session.add(row)
        result.embedded += 1
    session.commit()
    return result


def search(
    session: Session,
    query: str,
    provider: EmbeddingProvider | None = None,
    k: int = 10,
) -> list[SearchHit]:
    """Return the top-k items most semantically similar to the query."""

    provider = _resolve(provider)
    query_vec = provider.embed([query])[0]

    rows = session.exec(select(ItemEmbedding)).all()
    scored: list[SearchHit] = []
    for row in rows:
        item = session.get(Item, row.item_id)
        if item is None:
            continue
        scored.append(SearchHit(item=item, score=cosine_dense(query_vec, row.vector)))
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:k]


def embeddings_for_items(session: Session, item_ids: list[int]) -> dict[int, list[float]]:
    rows = session.exec(
        select(ItemEmbedding).where(ItemEmbedding.item_id.in_(item_ids))
    ).all()
    return {r.item_id: r.vector for r in rows}
