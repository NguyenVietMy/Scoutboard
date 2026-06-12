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
scoutboard source add rss https://example.com/feed.xml
scoutboard ingest
scoutboard classify
scoutboard cluster
scoutboard brief --cluster 1 --format md
scoutboard digest --week
scoutboard serve                               # local web UI
```

## JSONL import format

Each line is one normalized item:

```json
{"source":"youtube","source_url":"https://...","external_id":"youtube:comment:123","title":"...","body":"...","author":"handle","published_at":"2026-06-12T10:30:00Z","engagement":{"likes":123,"comments":45,"views":12000},"parent":{"type":"video","title":"...","url":"https://..."},"raw_payload":{}}
```

## Pipeline

```
collect public signals -> detect repeated unmet needs -> review evidence -> generate cited brief
```

See `MVP.md` for the full product thesis and scope.
