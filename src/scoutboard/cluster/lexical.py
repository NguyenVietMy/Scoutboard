"""Local lexical clustering — TF-IDF cosine similarity with a tool-overlap boost.

No API, no vector database (MVP non-goal: complex vector infra). A signal's
"document" is its topic terms + item title/body, plus the tools it mentions.
Clustering is greedy/leader-style: each document joins the most similar existing
cluster above a threshold, or starts a new one. This is transparent and cheap;
an optional embedding backend can be slotted in later via ``cluster.embeddings``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from scoutboard.signals.rules import _STOPWORDS

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+\-]{2,}")


def tokenize(text: str) -> list[str]:
    return [
        w for w in (m.group(0).lower() for m in _WORD.finditer(text or "")) if w not in _STOPWORDS
    ]


@dataclass
class ClusterDoc:
    """One clusterable unit, derived from a signal + its item."""

    item_id: int
    terms: Counter = field(default_factory=Counter)
    tools: set[str] = field(default_factory=set)
    # Carried through for cluster metadata / evidence / transparent sorting.
    source: str = ""
    title: str | None = None
    snippet: str | None = None
    engagement: float = 0.0
    published_at: datetime | None = None

    # Filled by vectorize():
    vector: dict[str, float] = field(default_factory=dict)


def build_doc(
    item_id: int,
    *,
    topic_terms: list[str],
    tools: list[str],
    title: str | None,
    body: str | None,
    source: str,
    engagement: float,
    snippet: str | None,
    published_at: datetime | None = None,
) -> ClusterDoc:
    terms = Counter(tokenize(f"{title or ''} {body or ''}"))
    # Topic terms (from rules/AI) are higher-signal — weight them up.
    for t in topic_terms:
        terms[t.lower()] += 3
    for t in tools:
        terms[t.lower()] += 2
    return ClusterDoc(
        item_id=item_id,
        terms=terms,
        tools={t.lower() for t in tools},
        source=source,
        title=title,
        snippet=snippet,
        engagement=engagement,
        published_at=published_at,
    )


def vectorize(docs: list[ClusterDoc]) -> None:
    """Compute unit-normalized TF-IDF vectors in place."""

    n = len(docs)
    if n == 0:
        return
    df: Counter = Counter()
    for doc in docs:
        df.update(doc.terms.keys())

    for doc in docs:
        total = sum(doc.terms.values()) or 1
        vec: dict[str, float] = {}
        for term, count in doc.terms.items():
            tf = count / total
            idf = math.log(n / (1 + df[term])) + 1.0
            vec[term] = tf * idf
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        doc.vector = {t: w / norm for t, w in vec.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    # Iterate the smaller vector for speed.
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


@dataclass
class _Group:
    members: list[int] = field(default_factory=list)  # indices into docs
    centroid: dict[str, float] = field(default_factory=dict)
    tools: set[str] = field(default_factory=set)


def _add_to_centroid(group: _Group, doc: ClusterDoc) -> None:
    k = len(group.members)
    new: dict[str, float] = dict(group.centroid)
    for t, w in doc.vector.items():
        new[t] = (group.centroid.get(t, 0.0) * k + w) / (k + 1)
    norm = math.sqrt(sum(v * v for v in new.values())) or 1.0
    group.centroid = {t: v / norm for t, v in new.items()}


def cluster_docs(
    docs: list[ClusterDoc],
    *,
    threshold: float = 0.18,
    tool_bonus: float = 0.1,
) -> list[list[int]]:
    """Greedy clustering. Returns a list of clusters, each a list of doc indices."""

    vectorize(docs)
    groups: list[_Group] = []
    for idx, doc in enumerate(docs):
        best_group: _Group | None = None
        best_score = 0.0
        for group in groups:
            score = cosine(doc.vector, group.centroid)
            shared = len(doc.tools & group.tools)
            if shared:
                score += tool_bonus * min(shared, 3)
            if score > best_score:
                best_score = score
                best_group = group
        if best_group is not None and best_score >= threshold:
            _add_to_centroid(best_group, doc)
            best_group.members.append(idx)
            best_group.tools |= doc.tools
        else:
            g = _Group(members=[idx], centroid=dict(doc.vector), tools=set(doc.tools))
            groups.append(g)
    return [g.members for g in groups]


def top_terms(docs: list[ClusterDoc], member_indices: list[int], limit: int = 6) -> list[str]:
    agg: Counter = Counter()
    for i in member_indices:
        agg.update(docs[i].terms)
    return [t for t, _ in agg.most_common(limit)]


def representative_index(docs: list[ClusterDoc], member_indices: list[int]) -> int:
    """The most engaged member is the cluster's representative evidence."""

    return max(member_indices, key=lambda i: docs[i].engagement)
