"""Anthropic client wrapper.

Centralizes model selection, the API-key check, and the two AI tasks Scoutboard
performs: cheap structured classification (Claude Haiku) and longer-form brief /
digest generation (Claude Opus, adaptive thinking). Keeping this in one module
means the rest of the codebase never imports ``anthropic`` directly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from scoutboard.config import get_settings

# The five MVP intent buckets plus an explicit escape hatch.
IntentLiteral = Literal[
    "request", "complaint", "comparison", "migration", "integration", "unknown"
]


class SignalClassification(BaseModel):
    """Structured output schema for per-signal classification."""

    intent: IntentLiteral
    topic_terms: list[str] = Field(default_factory=list)
    mentioned_tools: list[str] = Field(default_factory=list)
    problem_phrase: str = ""
    confidence: float = 0.0


class LLMError(RuntimeError):
    """Raised when an AI call is attempted without a key, or the API fails."""


_CLASSIFY_SYSTEM = (
    "You label public posts/comments/issues for a product-opportunity research tool. "
    "Classify the item into exactly one intent bucket: "
    "request (someone asking for a tool/feature), complaint (frustration with an existing "
    "tool or its pricing), comparison (weighing tools against each other), migration "
    "(moving away from a tool), or integration (wanting tools to connect). Use 'unknown' "
    "only if none fit. Extract 3-8 short lowercase topic_terms (keywords, not sentences), "
    "any mentioned_tools or competitors by name, a concise problem_phrase quoting the core "
    "ask in the author's words, and a confidence in [0,1]. Be faithful to the text; do not invent."
)


class LLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None  # lazy: don't import anthropic unless used

    @property
    def available(self) -> bool:
        return self._settings.has_ai

    def _anthropic(self):
        if not self.available:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Set it to enable AI classification/briefs, "
                "or run rule-only steps."
            )
        if self._client is None:
            import anthropic  # imported lazily so the package works without the dep present

            self._client = anthropic.Anthropic(api_key=self._settings.anthropic_api_key)
        return self._client

    def classify_signal(self, text: str) -> SignalClassification:
        """Classify a single candidate signal using the cheap model + structured output."""

        client = self._anthropic()
        response = client.messages.parse(
            model=self._settings.classify_model,
            max_tokens=512,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": text[:6000]}],
            output_format=SignalClassification,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError("classification returned no structured output")
        return parsed

    def generate_markdown(self, system: str, user: str, max_tokens: int = 4000) -> str:
        """Generate long-form Markdown (briefs/digest) with the stronger model.

        Uses adaptive thinking; streams to stay under HTTP timeouts on large output.
        """

        client = self._anthropic()
        chunks: list[str] = []
        with client.messages.stream(
            model=self._settings.brief_model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()
        for block in message.content:
            if block.type == "text":
                chunks.append(block.text)
        return "".join(chunks).strip()
