"""GitHub issues adapter (core open-source source).

Pulls issues from a repo via the REST API. Pull requests are filtered out (the
issues endpoint includes them). GitHub Discussions are intentionally deferred
(MVP.md says "later"). A token (``GITHUB_TOKEN``) lifts the rate limit.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import httpx

from scoutboard.ingest.base import AdapterError
from scoutboard.schemas import Engagement, NormalizedItem


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # GitHub timestamps are ISO-8601 with a trailing "Z".
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_issues(issues: list[dict], repo: str) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    for issue in issues:
        if "pull_request" in issue:
            continue  # the issues endpoint also returns PRs
        number = issue.get("number")
        if number is None:
            continue
        reactions = issue.get("reactions") or {}
        items.append(
            NormalizedItem(
                source="github",
                external_id=f"github:{repo}#{number}",
                source_url=issue.get("html_url", ""),
                title=issue.get("title"),
                body=issue.get("body") or "",
                author=(issue.get("user") or {}).get("login"),
                published_at=_parse_dt(issue.get("created_at")),
                engagement=Engagement(
                    likes=reactions.get("total_count"),
                    comments=issue.get("comments"),
                ),
                parent={"type": "repo", "title": repo, "url": f"https://github.com/{repo}"},
                tags=[lbl.get("name") for lbl in issue.get("labels", []) if lbl.get("name")],
                raw_payload=issue,
            )
        )
    return items


class GitHubIssuesAdapter:
    kind = "github"

    def __init__(self, repo: str, token: str | None = None, limit: int = 50, state: str = "all"):
        if "/" not in repo:
            raise AdapterError(f"repo must be 'owner/name', got '{repo}'")
        self.repo = repo
        self.token = token
        self.limit = limit
        self.state = state

    @classmethod
    def from_config(cls, config: dict, token: str | None = None) -> GitHubIssuesAdapter:
        return cls(
            repo=config["repo"],
            token=token,
            limit=int(config.get("limit", 50)),
            state=config.get("state", "all"),
        )

    def fetch(self) -> Iterable[NormalizedItem]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = f"https://api.github.com/repos/{self.repo}/issues"
        params = {"state": self.state, "per_page": min(self.limit, 100), "sort": "created"}
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network path
            raise AdapterError(f"GitHub fetch failed: {exc}") from exc
        return parse_issues(resp.json(), self.repo)
