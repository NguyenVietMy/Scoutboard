"""Reddit + GitHub Discussions adapters: pure parsers, config guards, runner wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scoutboard.ingest.base import AdapterError
from scoutboard.ingest.github_discussions import GitHubDiscussionsAdapter, parse_discussions
from scoutboard.ingest.reddit import RedditAdapter, parse_listing
from scoutboard.ingest.runner import build_adapter
from scoutboard.models import Source

FIXTURES = Path(__file__).parent / "fixtures"


# --- Reddit --------------------------------------------------------------------


def test_parse_reddit_listing():
    payload = json.loads((FIXTURES / "reddit_listing.json").read_text())
    items = parse_listing(payload, "selfhosted")
    assert len(items) == 2
    first = items[0]
    assert first.source == "reddit"
    assert first.external_id == "reddit:t3_abc123"
    assert first.source_url.startswith("https://www.reddit.com/r/selfhosted/")
    assert first.engagement.likes == 142
    assert first.engagement.comments == 37
    assert first.parent.title == "r/selfhosted"
    assert "Question" in first.tags


def test_reddit_requires_credentials():
    class _S:
        reddit_client_id = None
        reddit_client_secret = None
        reddit_user_agent = "x"

    with pytest.raises(AdapterError):
        RedditAdapter.from_config({"subreddit": "selfhosted"}, _S())


# --- GitHub Discussions --------------------------------------------------------


def test_parse_github_discussions():
    payload = json.loads((FIXTURES / "github_discussions.json").read_text())
    items = parse_discussions(payload, "owner/name")
    assert len(items) == 2
    first = items[0]
    assert first.source == "github_discussions"
    assert first.external_id == "github_discussion:owner/name#7"
    assert first.engagement.likes == 21
    assert first.engagement.comments == 9
    assert "Ideas" in first.tags
    assert first.published_at is not None


def test_github_discussions_requires_token():
    with pytest.raises(AdapterError):
        GitHubDiscussionsAdapter(repo="owner/name", token=None)
    with pytest.raises(AdapterError):
        GitHubDiscussionsAdapter(repo="bad-repo", token="tok")


# --- runner wiring -------------------------------------------------------------


def test_runner_builds_discussions_adapter(monkeypatch):
    import scoutboard.ingest.runner as runner

    class _S:
        github_token = "tok"

    monkeypatch.setattr(runner, "get_settings", lambda: _S())
    adapter = build_adapter(Source(kind="github_discussions", config={"repo": "owner/name"}))
    assert adapter.kind == "github_discussions"


def test_runner_builds_reddit_adapter(monkeypatch):
    import scoutboard.ingest.runner as runner

    class _S:
        reddit_client_id = "id"
        reddit_client_secret = "secret"
        reddit_user_agent = "ua"

    monkeypatch.setattr(runner, "get_settings", lambda: _S())
    adapter = build_adapter(Source(kind="reddit", config={"subreddit": "selfhosted"}))
    assert adapter.kind == "reddit"
