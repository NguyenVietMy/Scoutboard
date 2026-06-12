"""Rule-based candidate signal detection (MVP.md §AI Layer, pipeline step 3).

Cheap, deterministic, and AI-free. We only treat an item as a *candidate signal*
if its text matches at least one intent rule — this is the cost-control gate
before any AI is spent (pipeline step 4). Output is a ``SignalDraft`` that maps
straight onto the ``signals`` table.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from scoutboard.models import Intent

# Intent buckets and the phrases that hint at them. Lowercased substring/word match.
INTENT_PATTERNS: dict[str, list[str]] = {
    Intent.request.value: [
        "looking for", "is there a", "is there an", "anyone know", "anyone using",
        "recommend", "need a", "need an", "want a", "want an", "wish there was",
        "any tool", "any tools", "how do i", "suggestions for", "alternative to",
        "alternatives to", "open-source alternative", "open source alternative",
    ],
    Intent.complaint.value: [
        "too expensive", "so expensive", "overpriced", "hate ", "frustrat", "annoying",
        "is broken", "doesn't work", "does not work", "pain ", "painful", "sucks",
        "terrible", "buggy", "clunky", "too slow", "can't stand",
    ],
    Intent.comparison.value: [
        " vs ", " versus ", "compare", "comparison", "better than", "difference between",
        "or should i use",
    ],
    Intent.migration.value: [
        "migrat", "moving from", "move from", "switch from", "switching from",
        "leaving ", "moved off", "replace ", "replacing ", "moving off",
    ],
    Intent.integration.value: [
        "integrat", "connect to", "connect with", "webhook", "api for", "sync with",
        "plugin for", "works with", "hook up", "zapier",
    ],
}

# A small gazetteer of tools/competitors commonly named by builders. Pattern-based
# capture (below) generalizes beyond this list.
KNOWN_TOOLS = {
    "clay", "airtable", "apollo", "n8n", "zapier", "notion", "supabase", "firebase",
    "salesforce", "hubspot", "stripe", "retool", "make", "postgres", "mongodb",
    "snowflake", "segment", "amplitude", "mixpanel", "datadog", "vercel", "netlify",
    "github", "gitlab", "linear", "jira", "slack", "discord", "openai", "anthropic",
    "langchain", "pinecone", "weaviate", "elasticsearch", "redis",
}

# Capture the token following a migration/alternative trigger, e.g. "alternative to Clay".
_TOOL_CAPTURE = re.compile(
    r"(?:alternative to|alternatives to|migrate from|migrating from|move from|"
    r"moving from|switch from|switching from|replace|replacing|instead of|vs\.?|versus)\s+"
    r"([A-Za-z][A-Za-z0-9.+\-]{1,30})",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "it", "its", "i", "we", "you", "they", "he", "she", "my", "our", "your", "their",
    "do", "does", "did", "doing", "have", "has", "had", "can", "could", "would", "should",
    "will", "shall", "may", "might", "must", "not", "no", "yes", "so", "as", "at", "by",
    "from", "up", "out", "about", "into", "than", "then", "there", "here", "what", "which",
    "who", "how", "why", "when", "where", "any", "some", "all", "more", "most", "much",
    "very", "just", "like", "use", "using", "used", "get", "got", "need", "want", "im",
    "ive", "dont", "doesnt", "cant", "wont", "youre", "thats", "anyone", "something",
    "looking", "really", "good", "great", "best", "better",
}

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+\-]{2,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SignalDraft:
    intent: str
    topic_terms: list[str] = field(default_factory=list)
    mentioned_tools: list[str] = field(default_factory=list)
    problem_phrase: str | None = None
    confidence: float = 0.0


def _matched_intents(text: str) -> list[tuple[str, int]]:
    """Return (intent, hit_count) for every intent with at least one match."""

    matches: list[tuple[str, int]] = []
    for intent, phrases in INTENT_PATTERNS.items():
        hits = sum(1 for p in phrases if p in text)
        if hits:
            matches.append((intent, hits))
    return matches


def extract_topic_terms(text: str, limit: int = 8) -> list[str]:
    counts = Counter(
        w for w in (m.group(0).lower() for m in _WORD.finditer(text)) if w not in _STOPWORDS
    )
    return [term for term, _ in counts.most_common(limit)]


def extract_tools(text: str) -> list[str]:
    found: dict[str, None] = {}  # preserve order, dedupe case-insensitively
    lowered = text.lower()
    for tool in KNOWN_TOOLS:
        if re.search(rf"\b{re.escape(tool)}\b", lowered):
            found.setdefault(tool.title(), None)
    for match in _TOOL_CAPTURE.finditer(text):
        token = match.group(1).strip(".,;:")
        if token and token.lower() not in _STOPWORDS:
            found.setdefault(token if token[:1].isupper() else token.title(), None)
    return list(found)


def _problem_phrase(text: str, phrases: list[str]) -> str | None:
    sentences = _SENTENCE_SPLIT.split(text.strip())
    for sentence in sentences:
        low = sentence.lower()
        if any(p in low for p in phrases):
            return sentence.strip()[:280]
    return sentences[0].strip()[:280] if sentences and sentences[0].strip() else None


def detect(text: str) -> SignalDraft | None:
    """Detect a candidate signal in item text, or None if nothing matches."""

    if not text or not text.strip():
        return None
    low = text.lower()
    matched = _matched_intents(low)
    if not matched:
        return None

    matched.sort(key=lambda x: x[1], reverse=True)
    primary_intent, top_hits = matched[0]
    all_phrases = [p for intent, _ in matched for p in INTENT_PATTERNS[intent]]

    total_hits = sum(h for _, h in matched)
    # Transparent confidence: saturating function of rule hits + intent agreement.
    confidence = min(1.0, 0.4 + 0.15 * total_hits + 0.1 * (len(matched) - 1))

    return SignalDraft(
        intent=primary_intent,
        topic_terms=extract_topic_terms(text),
        mentioned_tools=extract_tools(text),
        problem_phrase=_problem_phrase(text, all_phrases),
        confidence=round(confidence, 3),
    )
