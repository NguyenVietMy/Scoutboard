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


def parse_line(line: str) -> NormalizedItem | None:
    """Parse one JSONL line into a NormalizedItem, or None if invalid."""

    line = line.strip()
    if not line:
        return None
    try:
        return NormalizedItem.model_validate(json.loads(line))
    except (json.JSONDecodeError, ValidationError):
        return None


def iter_jsonl_text(text: str) -> Iterator[tuple[int, NormalizedItem | None]]:
    """Yield (line_number, item-or-None) for each non-blank line of JSONL text."""

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        yield lineno, parse_line(raw)


def iter_jsonl(path: Path) -> Iterator[tuple[int, NormalizedItem | None]]:
    """Yield (line_number, item-or-None) for each non-blank line of a JSONL file."""

    yield from iter_jsonl_text(path.read_text(encoding="utf-8"))


def _store_pairs(session: Session, pairs, result: IngestResult) -> None:
    for _lineno, item in pairs:
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


def import_jsonl(session: Session, path: Path) -> IngestResult:
    result = IngestResult()
    _store_pairs(session, iter_jsonl(path), result)
    session.commit()
    return result


def import_jsonl_dir(session: Session, directory: Path) -> IngestResult:
    """Import every ``*.jsonl`` file in a directory (bulk BYO-scraper import)."""

    result = IngestResult()
    for path in sorted(directory.glob("*.jsonl")):
        _store_pairs(session, iter_jsonl(path), result)
    session.commit()
    return result
