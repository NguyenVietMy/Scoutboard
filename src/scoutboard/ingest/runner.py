"""Wire configured Source rows to adapters and run ingestion."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from scoutboard.config import get_settings
from scoutboard.ingest.base import AdapterError, SourceAdapter
from scoutboard.ingest.connectors import ConnectorAdapter
from scoutboard.ingest.github import GitHubIssuesAdapter
from scoutboard.ingest.github_discussions import GitHubDiscussionsAdapter
from scoutboard.ingest.hackernews import HackerNewsAdapter
from scoutboard.ingest.normalize import IngestResult, store_items
from scoutboard.ingest.reddit import RedditAdapter
from scoutboard.ingest.rss import RSSAdapter
from scoutboard.models import Source


def build_adapter(source: Source) -> SourceAdapter:
    settings = get_settings()
    if source.kind == "hn":
        return HackerNewsAdapter.from_config(source.config)
    if source.kind == "rss":
        return RSSAdapter.from_config(source.config)
    if source.kind == "github":
        return GitHubIssuesAdapter.from_config(source.config, token=settings.github_token)
    if source.kind == "github_discussions":
        return GitHubDiscussionsAdapter.from_config(source.config, token=settings.github_token)
    if source.kind == "reddit":
        return RedditAdapter.from_config(source.config, settings)
    if source.kind == "connector":
        return ConnectorAdapter.from_config(source.config)
    raise AdapterError(f"unknown source kind '{source.kind}'")


@dataclass
class SourceRunResult:
    source_id: int
    kind: str
    label: str
    result: IngestResult | None = None
    error: str | None = None


def _label(source: Source) -> str:
    cfg = source.config
    if source.kind == "hn":
        return f"hn:{cfg.get('feed', 'story')}"
    if source.kind == "rss":
        return f"rss:{cfg.get('url', '')}"
    if source.kind == "github":
        return f"github:{cfg.get('repo', '')}"
    if source.kind == "github_discussions":
        return f"github_discussions:{cfg.get('repo', '')}"
    if source.kind == "reddit":
        return f"reddit:r/{cfg.get('subreddit', '')}"
    if source.kind == "connector":
        return f"connector:{cfg.get('name', '')}"
    return source.kind


def run_ingest(session: Session) -> list[SourceRunResult]:
    sources = session.exec(select(Source).where(Source.enabled == True)).all()  # noqa: E712
    results: list[SourceRunResult] = []
    for source in sources:
        run = SourceRunResult(source_id=source.id, kind=source.kind, label=_label(source))
        try:
            adapter = build_adapter(source)
            run.result = store_items(session, adapter.fetch())
        except AdapterError as exc:
            run.error = str(exc)
        results.append(run)
    return results
