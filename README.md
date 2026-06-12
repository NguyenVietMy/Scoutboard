# Scoutboard

Local-first, open-source **opportunity discovery workbench** for indie SaaS, local-first, and
open-source builders. Scoutboard monitors selected public feeds and imported public signals,
then turns repeated asks, complaints, comparisons, migration signals, and integration requests
into **cited opportunity clusters and Markdown briefs**.

> Find what people are repeatedly asking for before someone builds it.

Every generated insight traces back to original source items with URLs, timestamps, and evidence
snippets. No opportunity brief makes a claim without attached source evidence.

## Install

```bash
pip install -e .
scoutboard init
```

Set `ANTHROPIC_API_KEY` to enable AI classification, briefs, and the weekly digest. Ingestion,
rule-based signals, and clustering run without it.

## Quick start

```bash
scoutboard init
scoutboard import items ./signals.jsonl       # bring-your-own scraper output
scoutboard source add hn --feed ask
scoutboard source add github --repo owner/name
scoutboard source add github_discussions --repo owner/name
scoutboard source add reddit --subreddit selfhosted        # needs Reddit OAuth app
scoutboard source add rss https://example.com/feed.xml
scoutboard ingest
scoutboard classify
scoutboard cluster
scoutboard brief --cluster 1 --format md
scoutboard digest --week
scoutboard serve                               # local web UI
```

Reddit needs a free "script" OAuth app: set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.
GitHub Discussions uses the GraphQL API, so set `GITHUB_TOKEN`.

## JSONL import format

Each line is one normalized item:

```json
{"source":"youtube","source_url":"https://...","external_id":"youtube:comment:123","title":"...","body":"...","author":"handle","published_at":"2026-06-12T10:30:00Z","engagement":{"likes":123,"comments":45,"views":12000},"parent":{"type":"video","title":"...","url":"https://..."},"raw_payload":{}}
```

## Bring-your-own connectors

Legally-sensitive or richer sources (YouTube, Telegram, Zalo, TikTok, Facebook,
Product Hunt, private scrapers) are **not bundled**. Instead, a connector is any command
you provide whose stdout is import-items JSONL (the same schema above):

```bash
scoutboard connector add youtube -c "python my_youtube_scraper.py --channel foo"
scoutboard connector list
scoutboard connector run            # runs all connectors and imports their output
```

Connectors also run as part of `scoutboard ingest`. You can also bulk-import a folder of
JSONL files:

```bash
scoutboard import dir ./exports/
```

This keeps the open-source core clean and the legal boundary intact — you bring the
scraper, Scoutboard normalizes and analyzes the output.

## Scaling: Postgres, embeddings & semantic search

SQLite is the default and needs no setup. To use Postgres, install the extra and point
Scoutboard at your database:

```bash
pip install -e ".[postgres]"
$env:SCOUTBOARD_DATABASE_URL = "postgresql+psycopg://user:pass@localhost/scoutboard"
scoutboard init
```

Embeddings are optional and opt-in (Anthropic has no embeddings endpoint, so Scoutboard
uses Voyage AI by default — any provider can be plugged in). With `VOYAGE_API_KEY` set:

```bash
scoutboard embed                       # embed items
scoutboard search "open-source Clay alternative"   # semantic search
scoutboard cluster --use-embeddings    # cluster by meaning instead of TF-IDF
```

Without a key, clustering stays purely lexical and the core has zero vector dependencies.
Embeddings are stored as portable JSON vectors (SQLite or Postgres); pgvector can be
swapped in later for large corpora.

## Pipeline

```
collect public signals -> detect repeated unmet needs -> review evidence -> generate cited brief
```

See `MVP.md` for the full product thesis and scope.
