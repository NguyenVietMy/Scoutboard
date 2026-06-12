"""JSONL import bridge (MVP.md §JSONL Import Bridge).

Lets any external scraper feed Scoutboard without coupling the core to brittle
source-specific code. Each line is one normalized item.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError
from sqlmodel import Session

from scoutboard.ingest.normalize import IngestResult, store_item
from scoutboard.schemas import NormalizedItem


def iter_jsonl(path: Path) -> Iterator[tuple[int, NormalizedItem | None]]:
    """Yield (line_number, item-or-None) for each non-blank line.

    None means the line failed to parse/validate; the caller decides how to count it.
    """

    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                yield lineno, NormalizedItem.model_validate(data)
            except (json.JSONDecodeError, ValidationError):
                yield lineno, None


def import_jsonl(session: Session, path: Path) -> IngestResult:
    result = IngestResult()
    for _lineno, item in iter_jsonl(path):
        if item is None:
            result.failed += 1
            continue
        try:
            if store_item(session, item):
                result.inserted += 1
            else:
                result.skipped += 1
        except Exception:
            result.failed += 1
    session.commit()
    return result
