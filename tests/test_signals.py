"""Phase 2: signals — rule detection and the AI-refinement path (fake client)."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import select

from scoutboard.db import get_session
from scoutboard.ingest.jsonl import import_jsonl
from scoutboard.llm.client import SignalClassification
from scoutboard.models import Intent, Signal
from scoutboard.signals import rules
from scoutboard.signals.pipeline import classify, run_ai

FIXTURES = Path(__file__).parent / "fixtures"


# --- rules (pure) --------------------------------------------------------------


def test_detect_request_intent():
    draft = rules.detect("Is there an open-source Clay alternative for enrichment?")
    assert draft is not None
    assert draft.intent == Intent.request.value
    assert "Clay" in draft.mentioned_tools
    assert draft.confidence > 0


def test_detect_migration_intent_and_tools():
    draft = rules.detect("We are migrating from Airtable to a local-first stack.")
    assert draft is not None
    assert draft.intent == Intent.migration.value
    assert "Airtable" in draft.mentioned_tools


def test_detect_returns_none_for_non_signal():
    assert rules.detect("Happy Friday everyone, have a great weekend!") is None
    assert rules.detect("") is None


def test_topic_terms_drop_stopwords():
    terms = rules.extract_topic_terms("I am looking for a self-hosted enrichment tool")
    assert "enrichment" in terms
    assert "the" not in terms and "for" not in terms


# --- pipeline: rules over imported items ---------------------------------------


def test_run_rules_creates_candidates_and_is_idempotent(scoutboard_home):
    with get_session() as session:
        import_jsonl(session, FIXTURES / "signals.jsonl")

    with get_session() as session:
        report = classify(session, use_ai=False)
    # All three fixture items are intent-bearing.
    assert report.candidates == 3
    assert report.used_ai is False

    with get_session() as session:
        again = classify(session, use_ai=False)
        assert again.candidates == 0  # idempotent: no new signals
        assert len(session.exec(select(Signal)).all()) == 3


# --- AI refinement with a fake client (no network) -----------------------------


class _FakeClient:
    available = True

    def classify_signal(self, text: str) -> SignalClassification:
        return SignalClassification(
            intent="complaint",
            topic_terms=["pricing", "enrichment"],
            mentioned_tools=["Clay"],
            problem_phrase="Clay is too expensive",
            confidence=0.91,
        )


def test_run_ai_refines_rule_signals(scoutboard_home):
    with get_session() as session:
        import_jsonl(session, FIXTURES / "signals.jsonl")
        classify(session, use_ai=False)  # seed rule-level signals

    with get_session() as session:
        refined, failed = run_ai(session, _FakeClient())
        assert refined == 3
        assert failed == 0
        signals = session.exec(select(Signal)).all()
        assert all(s.method == "ai" for s in signals)
        assert all(s.intent == "complaint" for s in signals)
        assert all(s.confidence == 0.91 for s in signals)
