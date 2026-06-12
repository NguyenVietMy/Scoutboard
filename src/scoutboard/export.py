"""Export items, clusters, and briefs to CSV or JSON (MVP.md build step 14).

Provenance fields (source URLs, timestamps) are preserved so exported data stays
traceable outside Scoutboard.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from scoutboard.models import Cluster, Item, OpportunityBrief

WHAT = ("items", "clusters", "briefs")
FORMATS = ("csv", "json")


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _rows(session: Session, what: str) -> list[dict[str, Any]]:
    if what == "items":
        return [
            {
                "id": i.id,
                "source": i.source,
                "external_id": i.external_id,
                "source_url": i.source_url,
                "title": i.title,
                "body": i.body,
                "author": i.author,
                "published_at": _iso(i.published_at),
                "engagement_score": i.engagement_score,
                "parent_type": i.parent_type,
                "parent_title": i.parent_title,
                "parent_url": i.parent_url,
            }
            for i in session.exec(select(Item)).all()
        ]
    if what == "clusters":
        return [
            {
                "id": c.id,
                "label": c.label,
                "summary": c.summary,
                "topic_terms": list(c.topic_terms),
                "item_count": c.item_count,
                "state": c.state,
                "first_seen_at": _iso(c.first_seen_at),
                "latest_seen_at": _iso(c.latest_seen_at),
            }
            for c in session.exec(select(Cluster)).all()
        ]
    if what == "briefs":
        return [
            {
                "id": b.id,
                "cluster_id": b.cluster_id,
                "title": b.title,
                "created_at": _iso(b.created_at),
                "markdown": b.markdown,
            }
            for b in session.exec(select(OpportunityBrief)).all()
        ]
    raise ValueError(f"unknown export target '{what}' (choose one of {', '.join(WHAT)})")


def _to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        # Serialize list/dict cells (e.g. topic_terms) as JSON for CSV safety.
        writer.writerow(
            {k: json.dumps(v) if isinstance(v, list | dict) else v for k, v in row.items()}
        )
    return buffer.getvalue()


def export_data(session: Session, what: str, fmt: str) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format '{fmt}' (choose one of {', '.join(FORMATS)})")
    rows = _rows(session, what)
    if fmt == "json":
        return json.dumps(rows, indent=2, ensure_ascii=False)
    return _to_csv(rows)
