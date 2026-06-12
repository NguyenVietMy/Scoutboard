"""Deterministic, fully-cited brief body for the no-API-key path.

When ``ANTHROPIC_API_KEY`` is absent, Scoutboard still produces a useful brief by
templating the analytic sections from the evidence pack. Every claim cites real
evidence by [n], so provenance holds without any model call.
"""

from __future__ import annotations

from collections import Counter

from scoutboard.briefs.evidence import ClusterEvidence, EvidenceItem

_ANGLE = {
    "request": (
        "Builders are actively asking for this. A focused tool addressing "
        "“{label}” would meet demonstrated, unmet demand."
    ),
    "complaint": (
        "Frustration with {tools} points to room for a cheaper, simpler, or "
        "more reliable alternative."
    ),
    "migration": (
        "People are moving away from {tools}; a migration-friendly alternative "
        "could capture switchers at the moment they are looking."
    ),
    "comparison": (
        "Active comparison shopping signals an unsettled market — clear "
        "positioning against {tools} matters more than features."
    ),
    "integration": (
        "Demand to connect {tools} indicates a glue/integration opportunity "
        "rather than a net-new product."
    ),
}

_MVP = {
    "request": (
        "Ship the single most-requested capability evidenced above, plus an import/export path."
    ),
    "complaint": (
        "Rebuild the one workflow people complain about, priced or packaged to remove that pain."
    ),
    "migration": (
        "Offer a one-command importer from the tool people are leaving, then match its core flow."
    ),
    "comparison": (
        "Lead with a sharp comparison page and the one capability that decides the choice."
    ),
    "integration": (
        "Build the highest-demand connector first; treat it as the wedge, not a side feature."
    ),
}


def _cites(ns: list[int]) -> str:
    return f"[{', '.join(str(n) for n in ns)}]" if ns else ""


def _trim(text: str, length: int = 140) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def _by_intent(evidence: list[EvidenceItem]) -> dict[str, list[EvidenceItem]]:
    grouped: dict[str, list[EvidenceItem]] = {}
    for e in evidence:
        grouped.setdefault(e.intent or "unknown", []).append(e)
    return grouped


def build_offline_body(ev: ClusterEvidence) -> str:
    if not ev.evidence:
        return "## Summary\nNo evidence is attached to this cluster yet."

    dominant = ev.intents[0][0] if ev.intents else "mixed"
    tools_str = ", ".join(t for t, _ in ev.tools[:3]) or "existing tools"
    rep_ns = [e.n for e in ev.evidence if e.representative] or [ev.evidence[0].n]
    source_counts = Counter(e.source for e in ev.evidence)

    out: list[str] = []

    out.append("## Summary")
    out.append(
        f"{ev.item_count} item(s) across {len(ev.sources)} source(s) "
        f"({', '.join(ev.sources)}) describe a recurring **{dominant}** signal"
        f"{' around ' + tools_str if ev.tools else ''}. {_cites(rep_ns)}"
    )

    out.append("\n## What people are asking for")
    grouped = _by_intent(ev.evidence)
    ordered = [i for i, _ in ev.intents] or list(grouped)
    for intent in ordered:
        items = grouped.get(intent, [])
        if not items:
            continue
        asks = "; ".join(f'“{_trim(e.snippet)}” [{e.n}]' for e in items[:4])
        out.append(f"- **{intent}** — {asks}")

    out.append("\n## Who seems to care")
    breakdown = ", ".join(f"{src} ({cnt})" for src, cnt in source_counts.most_common())
    out.append(
        f"Posters across {breakdown}. "
        f"{_cites([e.n for e in ev.evidence[:3]])}"
    )

    out.append("\n## Existing tools or competitors")
    if ev.tools:
        for tool, n in ev.tools:
            matching = [e.n for e in ev.evidence if tool.lower() in (e.snippet or "").lower()]
            cites = _cites(matching[:3])
            out.append(f"- **{tool}** — named {n}× {cites}".rstrip())
    else:
        out.append("No competing tools were named in the evidence.")

    out.append("\n## Product opportunity angle")
    angle = _ANGLE.get(dominant, _ANGLE["request"])
    out.append(angle.format(label=ev.cluster.label, tools=tools_str))

    out.append("\n## Possible MVP")
    out.append(_MVP.get(dominant, _MVP["request"]))

    out.append("\n## Risks and why this might be noise")
    risks: list[str] = []
    if len(ev.sources) == 1:
        risks.append(
            f"All evidence comes from a single source ({ev.sources[0]}); cross-source "
            "validation is weak."
        )
    if ev.item_count < 3:
        risks.append(f"Small sample ({ev.item_count} item(s)) — could be noise, not a trend.")
    if not ev.tools:
        risks.append("No competing tool named — the need may be vague or already well served.")
    if ev.mentions_last_week == 0:
        risks.append("No mentions in the last 7 days — the signal may be stale.")
    risks.append(
        "Signals were matched by lightweight rules, so some evidence may be off-topic — "
        "skim the cited items before acting."
    )
    out.extend(f"- {r}" for r in risks)

    return "\n".join(out)
