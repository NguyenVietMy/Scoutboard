"""Reddit adapter (core source, OAuth + explicit compliance).

Reddit requires an authenticated OAuth app and a descriptive User-Agent. This
adapter uses the read-only client-credentials flow (a "script" app) and only
reads public listings — no posting, no user data beyond public handles. Parsing
is separated from fetching so it is testable against a canned listing payload.

Compliance notes (MVP.md §Source Strategy): supply your own app credentials via
REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET; respect Reddit's API terms and rate limits.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import httpx

from scoutboard.ingest.base import AdapterError
from scoutboard.schemas import Engagement, NormalizedItem

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"


def parse_listing(payload: dict, subreddit: str) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    for child in payload.get("data", {}).get("children", []):
        data = child.get("data", {})
        post_id = data.get("id")
        if not post_id:
            continue
        permalink = data.get("permalink", "")
        created = data.get("created_utc")
        published = datetime.fromtimestamp(created, tz=UTC) if created else None
        source_url = f"https://www.reddit.com{permalink}" if permalink else data.get("url", "")
        items.append(
            NormalizedItem(
                source="reddit",
                external_id=f"reddit:{data.get('name', 't3_' + post_id)}",
                source_url=source_url,
                title=data.get("title"),
                body=data.get("selftext") or "",
                author=data.get("author"),
                published_at=published,
                engagement=Engagement(
                    likes=data.get("score"),
                    comments=data.get("num_comments"),
                ),
                parent={
                    "type": "subreddit",
                    "title": f"r/{subreddit}",
                    "url": f"https://www.reddit.com/r/{subreddit}",
                },
                tags=[t for t in [data.get("link_flair_text")] if t],
                raw_payload=data,
            )
        )
    return items


class RedditAdapter:
    kind = "reddit"

    def __init__(
        self,
        subreddit: str,
        client_id: str | None,
        client_secret: str | None,
        user_agent: str,
        listing: str = "new",
        limit: int = 50,
    ):
        if not client_id or not client_secret:
            raise AdapterError(
                "Reddit needs REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (create a 'script' app)."
            )
        self.subreddit = subreddit
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.listing = listing
        self.limit = limit

    @classmethod
    def from_config(cls, config: dict, settings) -> RedditAdapter:
        return cls(
            subreddit=config["subreddit"],
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
            listing=config.get("listing", "new"),
            limit=int(config.get("limit", 50)),
        )

    def _token(self) -> str:
        try:
            resp = httpx.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                headers={"User-Agent": self.user_agent},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network path
            raise AdapterError(f"Reddit auth failed: {exc}") from exc
        return resp.json()["access_token"]

    def fetch(self) -> Iterable[NormalizedItem]:  # pragma: no cover - network path
        token = self._token()
        url = f"{API_BASE}/r/{self.subreddit}/{self.listing}"
        try:
            resp = httpx.get(
                url,
                params={"limit": self.limit},
                headers={"Authorization": f"Bearer {token}", "User-Agent": self.user_agent},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterError(f"Reddit fetch failed: {exc}") from exc
        return parse_listing(resp.json(), self.subreddit)
