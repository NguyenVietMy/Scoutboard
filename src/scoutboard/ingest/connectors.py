"""Bring-your-own connector adapter (MVP.md §Bring-Your-Own Connector Sources).

Richer/legally-sensitive sources (YouTube, Telegram, Zalo, TikTok, Facebook,
Product Hunt, private scrapers) are NOT bundled. Instead, a connector is any
command you provide that prints normalized items as JSONL to stdout — the same
schema as ``scoutboard import items``. Scoutboard runs the command and imports
the result, keeping the open-source core clean and the legal boundary intact.

A connector is just: a command whose stdout is import-items JSONL.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable

from scoutboard.ingest.base import AdapterError
from scoutboard.ingest.jsonl import iter_jsonl_text
from scoutboard.schemas import NormalizedItem


def run_command(command: str, *, timeout: int = 300) -> str:
    """Run a connector command and return its stdout (raises on failure)."""

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - timing dependent
        raise AdapterError(f"connector timed out after {timeout}s: {command}") from exc
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise AdapterError(f"connector exited {proc.returncode}: {stderr or command}")
    return proc.stdout


class ConnectorAdapter:
    """Runs a user-provided command and parses its JSONL stdout."""

    kind = "connector"

    def __init__(self, name: str, command: str, timeout: int = 300):
        if not command:
            raise AdapterError("connector requires a command")
        self.name = name
        self.command = command
        self.timeout = timeout

    @classmethod
    def from_config(cls, config: dict) -> ConnectorAdapter:
        return cls(
            name=config.get("name", "connector"),
            command=config["command"],
            timeout=int(config.get("timeout", 300)),
        )

    def fetch(self) -> Iterable[NormalizedItem]:
        stdout = run_command(self.command, timeout=self.timeout)
        return [item for _lineno, item in iter_jsonl_text(stdout) if item is not None]
