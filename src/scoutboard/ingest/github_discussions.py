"""GitHub Discussions adapter (core source).

Discussions are only available via the GraphQL API, which requires a token.
Parsing operates on the decoded GraphQL response so it is testable against a
canned payload with no network.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import httpx

from scoutboard.ingest.base import AdapterError
from scoutboard.schemas import Engagement, NormalizedItem

GRAPHQL_URL = "https://api.github.com/graphql"

_QUERY = """
query($owner: String!, $name: String!, $first: Int!) {
  repository(owner: $owner, name: $name) {
    discussions(first: $first, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        number title body url createdAt
        author { login }
        category { name }
        upvoteCount
        comments { totalCount }
      }
    }
  }
}
"""


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_discussions(payload: dict, repo: str) -> list[NormalizedItem]:
    repository = (payload.get("data") or {}).get("repository") or {}
    nodes = (repository.get("discussions") or {}).get("nodes") or []
    items: list[NormalizedItem] = []
    for node in nodes:
        number = node.get("number")
        if number is None:
            continue
        author = (node.get("author") or {}).get("login")
        category = (node.get("category") or {}).get("name")
        items.append(
            NormalizedItem(
                source="github_discussions",
                external_id=f"github_discussion:{repo}#{number}",
                source_url=node.get("url", ""),
                title=node.get("title"),
                body=node.get("body") or "",
                author=author,
                published_at=_parse_dt(node.get("createdAt")),
                engagement=Engagement(
                    likes=node.get("upvoteCount"),
                    comments=(node.get("comments") or {}).get("totalCount"),
                ),
                parent={"type": "repo", "title": repo, "url": f"https://github.com/{repo}"},
                tags=[category] if category else [],
                raw_payload=node,
            )
        )
    return items


class GitHubDiscussionsAdapter:
    kind = "github_discussions"

    def __init__(self, repo: str, token: str | None, limit: int = 50):
        if "/" not in repo:
            raise AdapterError(f"repo must be 'owner/name', got '{repo}'")
        if not token:
            raise AdapterError(
                "GitHub Discussions needs GITHUB_TOKEN (the GraphQL API requires auth)."
            )
        self.repo = repo
        self.token = token
        self.limit = limit

    @classmethod
    def from_config(cls, config: dict, token: str | None) -> GitHubDiscussionsAdapter:
        return cls(repo=config["repo"], token=token, limit=int(config.get("limit", 50)))

    def fetch(self) -> Iterable[NormalizedItem]:  # pragma: no cover - network path
        owner, name = self.repo.split("/", 1)
        try:
            resp = httpx.post(
                GRAPHQL_URL,
                json={
                    "query": _QUERY,
                    "variables": {"owner": owner, "name": name, "first": min(self.limit, 100)},
                },
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterError(f"GitHub Discussions fetch failed: {exc}") from exc
        data = resp.json()
        if data.get("errors"):
            raise AdapterError(f"GitHub GraphQL error: {data['errors']}")
        return parse_discussions(data, self.repo)
