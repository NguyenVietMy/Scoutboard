"""Source adapter contract.

An adapter knows how to turn one configured source into a stream of
``NormalizedItem``. Adapters never touch the database — normalization and dedup
live in ``ingest.normalize`` so every source funnels through one path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from scoutboard.schemas import NormalizedItem


@runtime_checkable
class SourceAdapter(Protocol):
    """Pulls items for a single configured source."""

    kind: str

    def fetch(self) -> Iterable[NormalizedItem]:
        """Yield normalized items. May perform network I/O."""
        ...


class AdapterError(RuntimeError):
    """Raised when an adapter cannot fetch (bad config, network, API error)."""
