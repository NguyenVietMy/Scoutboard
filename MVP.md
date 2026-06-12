# Scoutboard MVP

## Product Thesis

Scoutboard is a local-first, open-source opportunity discovery workbench for indie SaaS and local-first/open-source software builders.

It monitors selected public feeds and imported public signals, then turns repeated asks, complaints, comparisons, migration signals, and integration requests into cited opportunity clusters and Markdown briefs.

The product is not a generic brand sentiment dashboard. The sharper wedge is:

> Find what people are repeatedly asking for before someone builds it.

## Target User

The MVP is for a single technical user who wants to discover validated product ideas from public conversations.

Primary users:

- indie hackers
- local-first software builders
- open-source maintainers
- researchers tracking unmet needs in software markets

Later users may include startups, marketers, and product teams, but the MVP should stay focused on builders.

## Positioning

Use:

> Scoutboard helps builders discover repeated unmet needs from public conversations. It turns posts, comments, issues, and feeds into cited opportunity briefs.

Avoid:

> Open-source social listening dashboard.

The workbench should feel like an opportunity research inbox, not a sentiment analytics tool.

## Core Principle

Scoutboard must preserve provenance.

Every generated insight should trace back to original source items with URLs, timestamps, and evidence snippets. No opportunity brief should make a claim without attached source evidence.

## Source Strategy

Scoutboard should not try to win by being the best scraper. It should win by being the best local-first, provenance-preserving insight layer for public signals.

Sources are split into two tiers.

### Core Open-Source Sources

These ship in the public repo and should be safe, installable, and easy to maintain:

- Hacker News
- RSS feeds, including Substack RSS where available
- GitHub issues
- GitHub Discussions later
- Reddit later, through OAuth and explicit compliance handling

### Bring-Your-Own Connector Sources

These are supported through a normalized import interface instead of being bundled directly in the open-source repo:

- YouTube channels and comments
- Facebook pages
- Telegram groups
- Zalo groups
- TikTok channels
- Product Hunt-like launch pages
- private scrapers
- custom internal datasets

This keeps the open-source core clean while allowing richer private ingestion stacks to feed Scoutboard.

## Important Legal Boundary

Do not copy proprietary company scraper code into Scoutboard unless there is explicit permission to open-source it.

It is fine to reuse:

- architecture lessons
- adapter patterns
- scheduling ideas
- retry and cursor concepts
- normalized schemas
- operational learnings

It is not fine to reuse company-owned implementation code without permission.

## MVP Source Inputs

The first product should be feed-driven.

Users configure sources such as:

- HN feeds or story types
- GitHub repositories
- RSS feed URLs
- JSONL imports from external scrapers

Do not start with a broad keyword crawler across the whole internet.

## JSONL Import Bridge

The JSONL importer is a key MVP feature.

It allows any external scraper or private pipeline to feed Scoutboard without coupling Scoutboard to brittle source-specific scraping code.

Example command:

```bash
scoutboard import items ./signals.jsonl
```

Each line should represent one normalized item:

```json
{
  "source": "youtube",
  "source_url": "https://www.youtube.com/watch?v=example",
  "external_id": "youtube:comment:123",
  "title": "Video title",
  "body": "Comment or post text",
  "author": "public_handle",
  "published_at": "2026-06-12T10:30:00Z",
  "engagement": {
    "likes": 123,
    "comments": 45,
    "views": 12000
  },
  "parent": {
    "type": "video",
    "title": "Parent video title",
    "url": "https://www.youtube.com/watch?v=example"
  },
  "raw_payload": {}
}
```

## Normalized Item Schema

The MVP should normalize all source data into a common model:

- `source`
- `external_id`
- `source_url`
- `title`
- `body`
- `author`
- `published_at`
- `engagement`
- `parent`
- `tags`
- `raw_payload`
- `fetched_at`

The raw payload should always be retained for traceability.

## Initial Data Model

Keep the schema small.

### raw_items

- `id`
- `source`
- `external_id`
- `source_url`
- `raw_payload`
- `fetched_at`

### items

- `id`
- `raw_item_id`
- `source`
- `source_url`
- `title`
- `body`
- `author`
- `published_at`
- `engagement_score`
- `parent_type`
- `parent_title`
- `parent_url`

### signals

- `id`
- `item_id`
- `intent`
- `topic_terms`
- `mentioned_tools`
- `problem_phrase`
- `confidence`
- `created_at`

### clusters

- `id`
- `label`
- `summary`
- `topic_terms`
- `item_count`
- `first_seen_at`
- `latest_seen_at`
- `created_at`
- `updated_at`

### cluster_items

- `cluster_id`
- `item_id`
- `representative`
- `evidence_snippet`

### opportunity_briefs

- `id`
- `cluster_id`
- `title`
- `markdown`
- `created_at`

## Intent Buckets

Start with a small set of useful buckets:

- `request`
- `complaint`
- `comparison`
- `migration`
- `integration`

Later buckets:

- `pricing_pain`
- `bug_friction`
- `buying_intent`
- `launch`
- `recommendation`

Classification is useful, but clustering is the core product.

## Clusters Page

The clusters page is the main workbench view.

It is an inbox of repeated unmet needs discovered across configured sources.

A cluster groups related posts, comments, issues, or feed items that appear to describe the same problem, request, comparison, migration signal, or product opportunity.

Example cluster:

```text
People want open-source alternatives to Clay

Intent: request / migration
Sources: Hacker News, Reddit, GitHub issues
Items: 23
First seen: 2026-05-19
Last seen: 2026-06-11
Momentum: 8 mentions this week

Representative evidence:
- "Is there an open-source Clay alternative for enrichment workflows?" [HN]
- "Clay is too expensive for my side project..." [Reddit]
- "Looking for self-hosted lead enrichment tooling..." [GitHub]

Mentioned tools:
Clay, Airtable, Apollo, n8n

Opportunity angle:
A local-first enrichment workflow tool for indie founders who cannot justify Clay pricing.
```

### Cluster States

- `new`: fresh clusters or materially updated clusters
- `tracking`: clusters the user marked as interesting
- `archived`: noisy or weak clusters hidden from the main workflow

### Cluster Filters

- source
- intent
- time range
- minimum item count
- topic tags
- mentioned tool or competitor
- has brief
- no brief

### Cluster Sorts

- newest activity
- fastest growing
- most evidence
- highest source diversity
- most recent

Avoid opaque opportunity scores in the MVP. Prefer transparent signals:

- frequency
- recency
- source diversity
- evidence quality
- direct asks
- complaints
- migrations

## Opportunity Brief

The Markdown opportunity brief is the first killer output.

It should include:

- title
- short summary
- what people are asking for
- evidence snippets with source links
- frequency and recency
- who seems to care
- existing tools or competitors mentioned
- product opportunity angle
- possible MVP
- risks and reasons this may be noise

Every claim should cite source items.

Example command:

```bash
scoutboard brief --cluster 12 --format md
```

## Weekly Digest

The weekly digest should summarize the most interesting new or changed clusters.

It should include:

- top new clusters
- clusters with growing activity
- notable repeated complaints
- notable migration signals
- brief links or generated Markdown sections

Example command:

```bash
scoutboard digest --week
```

## AI Layer

AI is allowed in the MVP.

Use AI for:

- extraction
- classification
- clustering assistance
- cluster labels
- summarization
- opportunity briefs

Do not make opaque sentiment scoring the main product.

Better AI outputs:

- what people are asking for
- evidence examples
- frequency and recency
- who seems to care
- competitors or alternatives mentioned
- product opportunity angle
- possible MVP
- why the signal may be misleading

For cost control, avoid classifying every raw item with AI if not needed. A practical first pipeline is:

1. ingest source items
2. normalize text
3. apply lightweight rules to identify candidate signals
4. use AI on candidate signals and cluster summaries
5. generate briefs only when requested or during digest generation

## MVP Architecture

Recommended stack:

- Python
- FastAPI
- Typer or Click CLI
- SQLite for MVP
- SQLModel or SQLAlchemy
- background jobs through a simple local worker first
- local web UI for the clusters page
- Markdown export
- JSONL import/export

Postgres and vector search can come later.

## CLI Shape

Example commands:

```bash
scoutboard init
scoutboard source add hn --feed ask
scoutboard source add github --repo langchain-ai/langchain
scoutboard source add rss https://example.com/feed.xml
scoutboard import items ./signals.jsonl

scoutboard ingest
scoutboard classify
scoutboard cluster
scoutboard brief --cluster 12 --format md
scoutboard digest --week
scoutboard serve
```

## Local Web UI

Even with an API/CLI-first product, the MVP should include a minimal local UI for browsing clusters.

The UI should prioritize:

- cluster inbox
- evidence review
- filters and sorting
- brief generation
- digest review
- source configuration later

The first UI does not need to be a full analytics dashboard.

## Build Order

1. Create installable Python package.
2. Add SQLite database and normalized item schema.
3. Add JSONL item importer.
4. Add Hacker News adapter.
5. Add RSS adapter.
6. Add GitHub issues adapter.
7. Add rule-based candidate signal extraction.
8. Add AI-assisted classification for candidate signals.
9. Add simple clustering.
10. Add Markdown opportunity brief generator.
11. Add weekly digest generator.
12. Add local clusters page.
13. Add source configuration.
14. Add export to CSV and JSON.

## Non-Goals For MVP

- generic brand sentiment dashboard
- broad social media monitoring
- team accounts
- hosted SaaS
- opaque opportunity scoring
- X/Twitter ingestion
- bundled scraping for legally sensitive sources
- polished enterprise dashboard
- real-time streaming
- complex vector infrastructure

## MVP Success Test

Scoutboard succeeds if a user can install it, configure a few feeds, import external scraper output, and produce at least one useful cited opportunity brief that they would act on or share.

The first version should optimize for this loop:

```text
collect public signals -> detect repeated unmet needs -> review evidence -> generate cited brief
```

