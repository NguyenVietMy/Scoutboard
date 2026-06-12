"""Optional embedding backend for clustering and semantic search.

The shipping default is lexical (``cluster.lexical``) so the core repo has zero
vector dependencies (MVP non-goal: complex vector infra). Anthropic has no
embeddings endpoint, so the default pluggable provider targets Voyage AI over
plain HTTP — opt-in via ``VOYAGE_API_KEY``. Any object with an ``embed(texts)``
method can be substituted (e.g. a local model) by overriding ``get_provider``.
"""

from __future__ import annotations

import math
from typing import Protocol, runtime_checkable

import httpx

from scoutboard.config import get_settings


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Maps texts to dense unit-comparable vectors."""

    model: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class VoyageEmbeddingProvider:
    """Voyage AI embeddings over HTTP (no SDK dependency)."""

    URL = "https://api.voyageai.com/v1/embeddings"

    def __init__(self, api_key: str, model: str = "voyage-3", batch_size: int = 128):
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for start in range(0, len(texts), self.batch_size):
            batch = [t or " " for t in texts[start : start + self.batch_size]]
            resp = httpx.post(
                self.URL,
                headers=headers,
                json={"input": batch, "model": self.model},
                timeout=60.0,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return out


def get_provider() -> EmbeddingProvider | None:
    """Return a configured embedding provider, or None when embeddings are off.

    None is the MVP default (no key / not enabled). Override this function to plug
    in a different backend.
    """

    settings = get_settings()
    if settings.has_embeddings:
        return VoyageEmbeddingProvider(settings.voyage_api_key, model=settings.voyage_model)
    return None


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def cosine_dense(a: list[float], b: list[float]) -> float:
    """Cosine similarity for dense vectors of equal length."""

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
