"""Hacker News adapter (core open-source source).

Uses the Algolia HN Search API, which exposes story-type feeds directly and
returns clean JSON. Parsing is separated from fetching so it can be tested
against a canned payload with no network.
"""

from __future__ import annotations

import html
from collections.abc import Iterable
from datetime import UTC, datetime

import httpx

from scoutboard.ingest.base import AdapterError
from scoutboard.schemas import Engagement, NormalizedItem

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"

# `scoutboard source add hn --feed <name>` -> Algolia tag.
FEED_TAGS = {
    "ask": "ask_hn",
    "show": "show_hn",
    "story": "story",
    "front": "front_page",
    "poll": "poll",
}


def parse_hits(hits: list[dict], feed: str) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    for hit in hits:
        object_id = str(hit.get("objectID") or "").strip()
        if not object_id:
            continue
        created = hit.get("created_at_i")
        published = datetime.fromtimestamp(created, tz=UTC) if created else None
        # Algolia returns HTML-escaped text (e.g. &#x27; &#x2f; &quot;); decode it
        # so stored bodies and all downstream tokenizing see real characters.
        raw_title = hit.get("title") or hit.get("story_title")
        title = html.unescape(raw_title) if raw_title else None
        body = html.unescape(hit.get("story_text") or hit.get("comment_text") or "")
        items.append(
            NormalizedItem(
                source="hn",
                external_id=f"hn:{object_id}",
                source_url=f"https://news.ycombinator.com/item?id={object_id}",
                title=title,
                body=body,
                author=hit.get("author"),
                published_at=published,
                engagement=Engagement(
                    likes=hit.get("points"),
                    comments=hit.get("num_comments"),
                ),
                tags=[f"hn:{feed}"],
                raw_payload=hit,
            )
        )
    return items


class HackerNewsAdapter:
    kind = "hn"

    def __init__(self, feed: str = "story", limit: int = 50):
        if feed not in FEED_TAGS:
            raise AdapterError(
                f"unknown HN feed '{feed}'. Choose one of: {', '.join(FEED_TAGS)}"
            )
        self.feed = feed
        self.limit = limit

    @classmethod
    def from_config(cls, config: dict) -> HackerNewsAdapter:
        return cls(feed=config.get("feed", "story"), limit=int(config.get("limit", 50)))

    def fetch(self) -> Iterable[NormalizedItem]:
        params = {"tags": FEED_TAGS[self.feed], "hitsPerPage": self.limit}
        try:
            resp = httpx.get(ALGOLIA_URL, params=params, timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network path
            raise AdapterError(f"HN fetch failed: {exc}") from exc
        return parse_hits(resp.json().get("hits", []), self.feed)
