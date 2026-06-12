"""Optional embedding backend for clustering — OFF by default.

The shipping default is purely lexical (``cluster.lexical``) so the core repo has
zero vector dependencies (MVP non-goal: complex vector infra). Anthropic has no
embeddings endpoint, so enabling this path means wiring a separate provider
(e.g. Voyage AI) behind ``EmbeddingProvider``. Left as a seam, not a dependency.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Maps texts to dense vectors. Implementations live outside the core repo."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


def get_provider() -> EmbeddingProvider | None:
    """Return a configured embedding provider, or None (the MVP default).

    Intentionally returns None: no provider ships with the open-source core. A
    downstream integration can override this to plug in a real backend.
    """

    return None
