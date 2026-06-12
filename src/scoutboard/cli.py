"""Scoutboard command-line interface.

The CLI is the primary surface (MVP.md §CLI Shape). Commands are thin wrappers
that delegate to the pipeline modules. Run ``scoutboard --help`` for the full list.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scoutboard import __version__
from scoutboard.config import get_settings
from scoutboard.db import get_session, init_db

app = typer.Typer(
    help="Scoutboard — discover repeated unmet needs from public conversations.",
    no_args_is_help=True,
    add_completion=False,
)
source_app = typer.Typer(help="Configure ingestion sources.", no_args_is_help=True)
import_app = typer.Typer(help="Import items from external files.", no_args_is_help=True)
connector_app = typer.Typer(
    help="Bring-your-own connectors (external commands that emit JSONL).",
    no_args_is_help=True,
)
app.add_typer(source_app, name="source")
app.add_typer(import_app, name="import")
app.add_typer(connector_app, name="connector")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"scoutboard {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """Scoutboard root command."""


@app.command()
def init() -> None:
    """Create the data directory and SQLite database (idempotent)."""

    settings = get_settings()
    settings.ensure_home()
    init_db()
    typer.echo(f"Initialized Scoutboard in {settings.home}")
    typer.echo(f"  database: {settings.db_path}")
    if not settings.has_ai:
        typer.echo(
            "  note: ANTHROPIC_API_KEY is not set — `classify`, `brief`, and "
            "`digest` need it for AI output."
        )


@source_app.command("add")
def source_add(
    kind: str = typer.Argument(..., help="Source kind: hn | rss | github"),
    url: str | None = typer.Argument(None, help="RSS feed URL (for kind=rss)"),
    feed: str = typer.Option("story", help="HN feed: ask | show | story | front | poll"),
    repo: str | None = typer.Option(None, help="GitHub repo as owner/name"),
    limit: int = typer.Option(50, help="Max items to fetch per run."),
) -> None:
    """Add a source.

    Examples: `source add hn --feed ask`, `source add github --repo owner/name`,
    `source add rss https://example.com/feed.xml`.
    """

    from scoutboard.models import Source

    kind = kind.lower()
    if kind == "hn":
        config = {"feed": feed, "limit": limit}
    elif kind == "rss":
        if not url:
            raise typer.BadParameter("rss source requires a feed URL")
        config = {"url": url, "limit": limit}
    elif kind == "github":
        if not repo:
            raise typer.BadParameter("github source requires --repo owner/name")
        config = {"repo": repo, "limit": limit}
    else:
        raise typer.BadParameter(f"unknown source kind '{kind}' (use hn | rss | github)")

    with get_session() as session:
        source = Source(kind=kind, config=config)
        session.add(source)
        session.commit()
        session.refresh(source)
        typer.echo(f"Added source #{source.id}: {kind} {config}")


@source_app.command("list")
def source_list() -> None:
    """List configured sources."""

    from sqlmodel import select

    from scoutboard.models import Source

    with get_session() as session:
        sources = session.exec(select(Source)).all()
        if not sources:
            typer.echo("No sources configured. Add one with `scoutboard source add ...`.")
            return
        for s in sources:
            status = "enabled" if s.enabled else "disabled"
            typer.echo(f"#{s.id}  {s.kind:<7} {status:<8} {s.config}")


@import_app.command("items")
def import_items(
    file: Path = typer.Argument(..., exists=True, readable=True, help="Path to a JSONL file."),
) -> None:
    """Import normalized items from a JSONL file (the BYO-scraper bridge)."""

    from scoutboard.ingest.jsonl import import_jsonl

    with get_session() as session:
        result = import_jsonl(session, file)
    typer.echo(
        f"Imported {result.inserted} new item(s); "
        f"{result.skipped} duplicate(s); {result.failed} invalid line(s)."
    )


@import_app.command("dir")
def import_dir(
    directory: Path = typer.Argument(
        ..., exists=True, file_okay=False, help="Folder of *.jsonl files."
    ),
) -> None:
    """Import every *.jsonl file in a directory (bulk BYO-scraper import)."""

    from scoutboard.ingest.jsonl import import_jsonl_dir

    with get_session() as session:
        result = import_jsonl_dir(session, directory)
    typer.echo(
        f"Imported {result.inserted} new item(s); "
        f"{result.skipped} duplicate(s); {result.failed} invalid line(s)."
    )


@connector_app.command("add")
def connector_add(
    name: str = typer.Argument(..., help="A name for this connector."),
    command: str = typer.Option(
        ..., "--command", "-c", help="Shell command that prints import-items JSONL to stdout."
    ),
) -> None:
    """Register a BYO connector (e.g. your YouTube/Telegram/private scraper)."""

    from scoutboard.models import Source

    with get_session() as session:
        source = Source(kind="connector", config={"name": name, "command": command})
        session.add(source)
        session.commit()
        session.refresh(source)
    typer.echo(f"Added connector #{source.id}: {name}")


@connector_app.command("list")
def connector_list() -> None:
    """List registered connectors."""

    from sqlmodel import select

    from scoutboard.models import Source

    with get_session() as session:
        rows = session.exec(select(Source).where(Source.kind == "connector")).all()
    if not rows:
        typer.echo("No connectors. Add one with `scoutboard connector add <name> -c '<command>'`.")
        return
    for s in rows:
        status = "enabled" if s.enabled else "disabled"
        name = s.config.get("name", "")
        command = s.config.get("command", "")
        typer.echo(f"#{s.id}  {name:<16} {status:<8} {command}")


@connector_app.command("run")
def connector_run(
    name: str | None = typer.Argument(None, help="Run only this connector (default: all)."),
) -> None:
    """Run connectors and import their output."""

    from sqlmodel import select

    from scoutboard.ingest.normalize import store_items
    from scoutboard.ingest.runner import build_adapter
    from scoutboard.models import Source

    with get_session() as session:
        stmt = select(Source).where(Source.kind == "connector", Source.enabled == True)  # noqa: E712
        connectors = [
            s for s in session.exec(stmt).all() if name is None or s.config.get("name") == name
        ]
        if not connectors:
            typer.echo("No matching connectors.")
            return
        for source in connectors:
            label = source.config.get("name", source.id)
            try:
                result = store_items(session, build_adapter(source).fetch())
                typer.echo(
                    f"  {label}: {result.inserted} new, {result.skipped} dup, "
                    f"{result.failed} failed"
                )
            except Exception as exc:  # noqa: BLE001 - surface connector errors to the user
                typer.echo(f"  {label}: ERROR — {exc}")


@app.command()
def ingest() -> None:
    """Fetch items from all enabled sources."""

    from scoutboard.ingest.runner import run_ingest

    with get_session() as session:
        runs = run_ingest(session)

    if not runs:
        typer.echo("No enabled sources. Add one with `scoutboard source add ...`.")
        return
    for run in runs:
        if run.error:
            typer.echo(f"  {run.label}: ERROR — {run.error}")
        else:
            r = run.result
            typer.echo(
                f"  {run.label}: {r.inserted} new, {r.skipped} dup, {r.failed} failed"
            )


@app.command()
def cluster(
    threshold: float | None = typer.Option(
        None, help="Similarity threshold (0-1). Lower = larger, looser clusters."
    ),
) -> None:
    """Group signals into opportunity clusters (rebuilds the cluster set)."""

    from scoutboard.cluster.build import build_clusters

    with get_session() as session:
        report = build_clusters(session, threshold=threshold)
    typer.echo(
        f"Built {report.clusters} cluster(s) "
        f"({report.multi_item_clusters} with multiple items) "
        f"covering {report.items_clustered} signal(s)."
    )


@app.command()
def classify(
    rules_only: bool = typer.Option(
        False, "--rules-only", help="Skip the AI pass; use rule-based signals only."
    ),
) -> None:
    """Detect candidate signals (rules) and refine them with AI when a key is set."""

    from scoutboard.signals.pipeline import classify as run_classify

    settings = get_settings()
    with get_session() as session:
        report = run_classify(session, use_ai=not rules_only)

    typer.echo(
        f"Scanned {report.scanned} item(s); created {report.candidates} candidate signal(s)."
    )
    if report.used_ai:
        typer.echo(f"AI refined {report.refined} signal(s); {report.ai_failed} failed.")
    elif rules_only:
        typer.echo("AI pass skipped (--rules-only).")
    elif not settings.has_ai:
        typer.echo("AI pass skipped: ANTHROPIC_API_KEY not set. Signals are rule-based.")


@app.command()
def brief(
    cluster: int = typer.Option(..., "--cluster", help="Cluster id to brief."),
    format: str = typer.Option("md", "--format", help="Output format (md)."),
    rules_only: bool = typer.Option(
        False, "--rules-only", help="Skip AI prose; emit the structured cited brief only."
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write to a file."),
) -> None:
    """Generate a cited Markdown opportunity brief for a cluster."""

    if format != "md":
        raise typer.BadParameter("only 'md' is supported in the MVP")

    from scoutboard.briefs.generator import generate_brief

    with get_session() as session:
        result = generate_brief(session, cluster, use_ai=not rules_only)
    if result is None:
        typer.echo(f"No cluster #{cluster} found.")
        raise typer.Exit(code=1)

    _title, markdown = result
    if output:
        output.write_text(markdown, encoding="utf-8")
        typer.echo(f"Wrote brief for cluster #{cluster} to {output}")
    else:
        typer.echo(markdown)


@app.command()
def digest(
    week: bool = typer.Option(False, "--week", help="Summarize the last 7 days."),
    days: int = typer.Option(7, "--days", help="Window size in days."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write to a file."),
) -> None:
    """Generate the weekly digest of notable new and changed clusters."""

    from scoutboard.briefs.digest import generate_digest

    window = 7 if week else days
    with get_session() as session:
        markdown = generate_digest(session, days=window)
    if output:
        output.write_text(markdown, encoding="utf-8")
        typer.echo(f"Wrote digest to {output}")
    else:
        typer.echo(markdown)


@app.command()
def export(
    what: str = typer.Option("items", "--what", help="items | clusters | briefs"),
    format: str = typer.Option("json", "--format", help="json | csv"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write to a file."),
) -> None:
    """Export items, clusters, or briefs to CSV or JSON."""

    from scoutboard.export import export_data

    try:
        with get_session() as session:
            payload = export_data(session, what, format)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if output:
        output.write_text(payload, encoding="utf-8")
        typer.echo(f"Exported {what} ({format}) to {output}")
    else:
        typer.echo(payload)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind."),
    port: int = typer.Option(8000, help="Port to bind."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload (development)."),
) -> None:
    """Launch the local web UI (cluster inbox, evidence review, briefs, digest)."""

    import uvicorn

    typer.echo(f"Scoutboard UI at http://{host}:{port}")
    uvicorn.run("scoutboard.web.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
