"""Generate cited Markdown opportunity briefs (MVP.md §Opportunity Brief).

A brief is the first killer output. The evidence list and stats come straight
from the database (provenance is structural), and Claude Opus writes the analytic
sections around that fixed, numbered evidence — citing it by [n].
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session

from scoutboard.briefs.evidence import ClusterEvidence, gather_cluster_evidence
from scoutboard.llm.client import LLMClient
from scoutboard.models import OpportunityBrief

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),  # Markdown, not HTML
        trim_blocks=True,
        lstrip_blocks=True,
    )


_BRIEF_SYSTEM = (
    "You write concise, skeptical opportunity briefs for software builders. You are given a "
    "cluster of public signals as NUMBERED evidence. Write Markdown with these sections, in "
    "order: '## Summary', '## What people are asking for', '## Who seems to care', "
    "'## Existing tools or competitors', '## Product opportunity angle', '## Possible MVP', "
    "'## Risks and why this might be noise'. EVERY factual claim must cite the evidence it "
    "rests on using bracketed numbers like [1] or [2,3] that refer to the provided evidence. "
    "Do not invent facts, URLs, or quotes beyond the evidence. Do NOT restate the metadata "
    "header or re-list the raw evidence — only the analytic sections above."
)


def _build_ai_body(evidence: ClusterEvidence, client: LLMClient) -> str | None:
    if not client.available:
        return None
    payload = (
        f"Cluster label: {evidence.cluster.label}\n"
        f"Item count: {evidence.item_count}\n"
        f"Intents: {', '.join(f'{i} ({n})' for i, n in evidence.intents) or 'n/a'}\n"
        f"Mentioned tools: {', '.join(f'{t} ({n})' for t, n in evidence.tools) or 'n/a'}\n\n"
        f"Numbered evidence:\n{evidence.as_prompt_block()}"
    )
    body = client.generate_markdown(_BRIEF_SYSTEM, payload, max_tokens=3000)
    return body or None


def render_brief(evidence: ClusterEvidence, ai_body: str | None) -> str:
    title = evidence.cluster.label.title() if evidence.cluster.label else "Opportunity"
    return _env().get_template("brief.md.j2").render(
        title=title,
        intents=", ".join(f"{i} ({n})" for i, n in evidence.intents),
        sources=", ".join(evidence.sources),
        item_count=evidence.item_count,
        first_seen=evidence.first_seen,
        last_seen=evidence.last_seen,
        mentions_last_week=evidence.mentions_last_week,
        tools=", ".join(t for t, _ in evidence.tools),
        ai_body=ai_body,
        evidence=evidence.evidence,
    )


def generate_brief(
    session: Session, cluster_id: int, *, use_ai: bool = True
) -> tuple[str, str] | None:
    """Generate, persist, and return (title, markdown) for a cluster's brief."""

    evidence = gather_cluster_evidence(session, cluster_id)
    if evidence is None:
        return None

    client = LLMClient()
    ai_body = _build_ai_body(evidence, client) if use_ai else None
    markdown = render_brief(evidence, ai_body)
    title = evidence.cluster.label.title() if evidence.cluster.label else "Opportunity"

    session.add(OpportunityBrief(cluster_id=cluster_id, title=title, markdown=markdown))
    session.commit()
    return title, markdown
