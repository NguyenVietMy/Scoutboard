"""RSS / Atom adapter (core open-source source), including Substack RSS.

``feedparser`` handles both RSS and Atom and a lot of real-world malformedness.
Parsing operates on a parsed feed object so tests can feed it a fixture string.
"""

from __future__ import annotations

import html
import re
import time
from collections.abc import Iterable
from datetime import UTC, datetime

import feedparser

from scoutboard.schemas import NormalizedItem

_TAG = re.compile(r"<[^>]+>")


def _clean_html(text: str | None) -> str:
    """RSS bodies/titles carry raw HTML; strip tags and decode entities so the
    stored text is readable and downstream tokenizing stays clean."""

    if not text:
        return ""
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text))).strip()


def _entry_published(entry) -> datetime | None:
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if struct:
        return datetime.fromtimestamp(time.mktime(struct), tz=UTC)
    return None


def _entry_body(entry) -> str:
    if entry.get("summary"):
        return _clean_html(entry["summary"])
    content = entry.get("content")
    if content:
        return _clean_html(content[0].get("value", ""))
    return ""


def parse_feed(parsed: feedparser.FeedParserDict, feed_url: str) -> list[NormalizedItem]:
    feed_title = parsed.feed.get("title") if parsed.get("feed") else None
    items: list[NormalizedItem] = []
    for entry in parsed.get("entries", []):
        link = entry.get("link") or feed_url
        external = entry.get("id") or link
        items.append(
            NormalizedItem(
                source="rss",
                external_id=f"rss:{external}",
                source_url=link,
                title=_clean_html(entry.get("title")) or None,
                body=_entry_body(entry),
                author=entry.get("author"),
                published_at=_entry_published(entry),
                parent={"type": "feed", "title": feed_title, "url": feed_url},
                raw_payload=dict(entry),
            )
        )
    return items


class RSSAdapter:
    kind = "rss"

    def __init__(self, url: str):
        self.url = url

    @classmethod
    def from_config(cls, config: dict) -> RSSAdapter:
        return cls(url=config["url"])

    def fetch(self) -> Iterable[NormalizedItem]:
        parsed = feedparser.parse(self.url)
        return parse_feed(parsed, self.url)
