"""Signal pipeline: rules over items, then optional AI refinement over candidates.

Matches MVP.md §AI Layer cost-control pipeline: rules find candidate signals
(cheap), and AI is only ever spent on those candidates — never on every raw item.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from scoutboard.llm.client import LLMClient, LLMError
from scoutboard.models import Item, Signal
from scoutboard.signals import rules


@dataclass
class ClassifyReport:
    scanned: int = 0          # items examined by the rules pass
    candidates: int = 0       # new candidate signals created
    refined: int = 0          # signals upgraded by AI
    ai_failed: int = 0        # AI calls that errored (signal kept at rules level)
    used_ai: bool = False


def _item_text(item: Item) -> str:
    return " ".join(p for p in (item.title, item.body) if p).strip()


def run_rules(session: Session) -> tuple[int, int]:
    """Create candidate signals for items that don't have one yet.

    Returns (scanned, candidates_created).
    """

    signaled_ids = set(session.exec(select(Signal.item_id)).all())
    items = session.exec(select(Item)).all()
    scanned = 0
    created = 0
    for item in items:
        if item.id in signaled_ids:
            continue
        scanned += 1
        draft = rules.detect(_item_text(item))
        if draft is None:
            continue
        session.add(
            Signal(
                item_id=item.id,
                intent=draft.intent,
                topic_terms=draft.topic_terms,
                mentioned_tools=draft.mentioned_tools,
                problem_phrase=draft.problem_phrase,
                confidence=draft.confidence,
                method="rules",
            )
        )
        created += 1
    session.commit()
    return scanned, created


def run_ai(session: Session, client: LLMClient) -> tuple[int, int]:
    """Refine rule-level signals with the AI classifier. Returns (refined, failed)."""

    pending = session.exec(select(Signal).where(Signal.method == "rules")).all()
    refined = 0
    failed = 0
    for signal in pending:
        item = session.get(Item, signal.item_id)
        if item is None:
            continue
        try:
            result = client.classify_signal(_item_text(item))
        except LLMError:
            failed += 1
            continue
        signal.intent = result.intent
        # Prefer AI terms/tools when present; fall back to the rule output.
        signal.topic_terms = result.topic_terms or signal.topic_terms
        signal.mentioned_tools = result.mentioned_tools or signal.mentioned_tools
        signal.problem_phrase = result.problem_phrase or signal.problem_phrase
        signal.confidence = result.confidence or signal.confidence
        signal.method = "ai"
        session.add(signal)
        refined += 1
    session.commit()
    return refined, failed


def classify(session: Session, use_ai: bool = True) -> ClassifyReport:
    report = ClassifyReport()
    report.scanned, report.candidates = run_rules(session)

    if use_ai:
        client = LLMClient()
        if client.available:
            report.used_ai = True
            report.refined, report.ai_failed = run_ai(session, client)
    return report
