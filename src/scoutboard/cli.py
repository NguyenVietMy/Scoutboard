"""Scoutboard command-line interface.

The CLI is the primary surface (MVP.md §CLI Shape). Commands are thin wrappers
that delegate to the pipeline modules. Run ``scoutboard --help`` for the full list.
"""

from __future__ import annotations

import typer

from scoutboard import __version__
from scoutboard.config import get_settings
from scoutboard.db import init_db

app = typer.Typer(
    help="Scoutboard — discover repeated unmet needs from public conversations.",
    no_args_is_help=True,
    add_completion=False,
)


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


if __name__ == "__main__":
    app()
