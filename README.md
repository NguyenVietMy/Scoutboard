# Scoutboard

Local-first, open-source **opportunity discovery workbench** for indie SaaS, local-first, and
open-source builders. Scoutboard monitors public feeds and imported signals, then turns repeated
asks, complaints, comparisons, migration signals, and integration requests into **cited
opportunity clusters and Markdown briefs**.

> Find what people are repeatedly asking for before someone builds it.

Every generated insight traces back to original source items with URLs, timestamps, and evidence
snippets. No opportunity brief makes a claim without attached source evidence.

## 5 minutes to your first brief

```bash
pip install -e .
scoutboard quickstart     # seeds key-free starter feeds (HN + Reddit/Lobsters RSS)
scoutboard ingest         # pull items from those feeds
scoutboard classify       # detect + (optionally) AI-refine signals
scoutboard cluster        # group repeated needs
scoutboard brief --cluster 1   # a cited opportunity brief
scoutboard serve          # browse the inbox in your browser
```

`quickstart` is idempotent and needs no API keys or accounts. `ingest` → `classify` → `cluster`
→ `brief` is the whole pipeline.

## Do I need an API key?

No — Scoutboard runs fully **offline** by default. Ingestion, rule-based signal detection,
clustering, and a complete (deterministic) offline brief all work with zero keys and zero cost.

Setting `ANTHROPIC_API_KEY` unlocks sharper output:

- **Classification** uses `claude-haiku-4-5` to refine intent and topic terms (cheap — fractions
  of a cent per signal, and only candidate signals are sent).
- **Briefs and the weekly digest** use `claude-opus-4-8` with adaptive thinking to write the prose
  *around* fixed, real citations.

Put keys in a `.env` file in your working directory (it is git-ignored):

```
ANTHROPIC_API_KEY=sk-ant-...
# optional
GITHUB_TOKEN=...                 # higher GitHub rate limits + Discussions
VOYAGE_API_KEY=...               # embeddings + semantic search
REDDIT_CLIENT_ID=...             # Reddit API (the RSS feeds above need none)
REDDIT_CLIENT_SECRET=...
```

If no key is set, `classify`/`brief`/`digest` automatically fall back to the rule-based and
offline paths and tell you so.

## Adding your own sources

```bash
scoutboard source add hn --feed ask                     # ask | show | story | front | poll
scoutboard source add github --repo owner/name          # GitHub issues
scoutboard source add github_discussions --repo owner/name
scoutboard source add reddit --subreddit selfhosted     # needs Reddit OAuth app
scoutboard source add rss https://example.com/feed.xml  # any RSS/Atom, incl. Substack
scoutboard source list
```

Core sources are Hacker News, RSS/Atom, GitHub issues, GitHub Discussions, and Reddit. Reddit's
public `.rss` feeds work through the RSS adapter with no OAuth; the native `reddit` source needs a
free "script" app (`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`).

## Bring-your-own connectors

Legally-sensitive or richer sources (YouTube, Telegram, Zalo, TikTok, Facebook, Product Hunt,
private scrapers) are **not bundled**. A connector is any command whose stdout is import-items
JSONL:

```bash
scoutboard connector add youtube -c "python my_youtube_scraper.py --channel foo"
scoutboard connector list
scoutboard connector run        # runs all connectors and imports their output
```

Connectors also run as part of `scoutboard ingest`. You can bulk-import a folder of JSONL files
with `scoutboard import dir ./exports/`. This keeps the open-source core clean and the legal
boundary intact — you bring the scraper, Scoutboard normalizes and analyzes the output.

### JSONL import format

Each line is one normalized item:

```json
{"source":"youtube","source_url":"https://...","external_id":"youtube:comment:123","title":"...","body":"...","author":"handle","published_at":"2026-06-12T10:30:00Z","engagement":{"likes":123,"comments":45,"views":12000},"parent":{"type":"video","title":"...","url":"https://..."},"raw_payload":{}}
```

## Scaling: Postgres, embeddings & semantic search

SQLite is the default and needs no setup. For Postgres:

```bash
pip install -e ".[postgres]"
export SCOUTBOARD_DATABASE_URL="postgresql+psycopg://user:pass@localhost/scoutboard"
scoutboard init
```

Embeddings are optional and opt-in (Anthropic has no embeddings endpoint, so Scoutboard uses
Voyage AI by default — any provider can be plugged in). With `VOYAGE_API_KEY` set:

```bash
scoutboard embed                                   # embed items
scoutboard search "open-source Clay alternative"   # semantic search
scoutboard cluster --use-embeddings                # cluster by meaning instead of TF-IDF
```

Without a key, clustering stays purely lexical and the core has zero vector dependencies.
Embeddings are stored as portable JSON vectors (SQLite or Postgres); pgvector can be swapped in
later for large corpora.

## Exporting

```bash
scoutboard export --what clusters --format json -o clusters.json   # items | clusters | briefs
```

## Pipeline

```
collect public signals -> detect repeated unmet needs -> review evidence -> generate cited brief
```

See `MVP.md` for the full product thesis and scope.

## License

MIT — see [LICENSE](LICENSE).
