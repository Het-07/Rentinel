"""
Retrieval over the scam-pattern knowledge base.

Two retrievers run together (hybrid):
- regex indicators: high precision, catch the exact phrasings fraudsters reuse;
- BM25 over example phrasings: catches paraphrases the regexes miss.

Both are local and need no model download. A dense-embedding retriever can be added later by
implementing the same `match` interface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rank_bm25 import BM25Okapi

from rentinel.text import sentences, tokenize

_NEGATION = re.compile(r"\b(?:never|not|no|don't|dont|won't|will not|do not|does not|doesn't|without|nor|beware of|"
                       r"avoid|scam|scams|scammers?|fraud)\b", re.I)


@dataclass
class Pattern:
    id: str
    title: str
    severity: float
    explanation: str
    sources: list[str]
    indicators: list[re.Pattern] = field(default_factory=list)
    exclude: list[re.Pattern] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


@dataclass
class PatternMatch:
    pattern: Pattern
    sentence: str
    method: str        # "indicator" or "bm25"
    strength: float    # 0-1


class KnowledgeBase:
    def __init__(self, path: str | Path):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.reviewed: str = str(data.get("reviewed", "unknown"))
        self.patterns: list[Pattern] = [
            Pattern(
                id=p["id"], title=p["title"], severity=float(p["severity"]),
                explanation=p.get("explanation", ""), sources=list(p.get("sources", [])),
                indicators=[re.compile(r, re.I) for r in p.get("indicators", [])],
                exclude=[re.compile(r, re.I) for r in p.get("exclude", [])],
                examples=list(p.get("examples", [])),
            )
            for p in data["patterns"]
        ]
        self._doc_pattern: list[Pattern] = []
        docs: list[list[str]] = []
        for p in self.patterns:
            for ex in p.examples:
                docs.append(tokenize(ex))
                self._doc_pattern.append(p)
        self._docs = docs
        self._bm25 = BM25Okapi(docs) if docs else None
        # "Anchor" terms: words that appear in one pattern's examples and no other's. A BM25 match must
        # share at least one, so generic overlaps ("security deposit ... only") don't trigger a pattern.
        owners: dict[str, set[str]] = {}
        for p, doc in zip(self._doc_pattern, docs):
            for t in doc:
                owners.setdefault(t, set()).add(p.id)
        self.anchors: dict[str, set[str]] = {}
        for t, ids in owners.items():
            if len(ids) == 1:
                self.anchors.setdefault(next(iter(ids)), set()).add(t)


class PatternRetriever:
    """Finds knowledge-base patterns present in a listing, sentence by sentence."""

    def __init__(self, kb: KnowledgeBase, top_n: int = 3, min_coverage: float = 0.5, min_overlap: int = 3):
        self.kb = kb
        self.top_n = top_n
        self.min_coverage = min_coverage
        self.min_overlap = min_overlap

    @staticmethod
    def _negated(sentence: str, start: int) -> bool:
        """True when the match sits after a negation/warning cue, e.g. 'we NEVER ask for a deposit before...'."""
        window = sentence[max(0, start - 40): start]
        return bool(_NEGATION.search(window))

    def _bm25_matches(self, sentence: str) -> list[PatternMatch]:
        if not self.kb._bm25:
            return []
        q = tokenize(sentence)
        if len(q) < self.min_overlap:
            return []
        scores = self.kb._bm25.get_scores(q)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[: self.top_n]
        out = []
        qset = set(q)
        for i in ranked:
            if scores[i] <= 0:
                continue
            doc = set(self.kb._docs[i])
            pattern = self.kb._doc_pattern[i]
            shared = doc & qset
            coverage = len(shared) / max(1, len(doc))
            if (len(shared) >= self.min_overlap and coverage >= self.min_coverage
                    and shared & self.kb.anchors.get(pattern.id, set()) and not _NEGATION.search(sentence)):
                out.append(PatternMatch(pattern, sentence, "bm25", round(0.8 * coverage, 3)))
        return out

    def match(self, text: str) -> list[PatternMatch]:
        best: dict[str, PatternMatch] = {}
        for sent in sentences(text):
            found: list[PatternMatch] = []
            for p in self.kb.patterns:
                if any(x.search(sent) for x in p.exclude):
                    continue
                for rx in p.indicators:
                    m = rx.search(sent)
                    if m and not self._negated(sent, m.start()):
                        found.append(PatternMatch(p, sent, "indicator", 1.0))
                        break
            found += self._bm25_matches(sent)
            for fm in found:
                cur = best.get(fm.pattern.id)
                if cur is None or fm.strength > cur.strength:
                    best[fm.pattern.id] = fm
        return sorted(best.values(), key=lambda m: m.pattern.severity * m.strength, reverse=True)
