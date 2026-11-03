"""RAG agent: retrieves documented scam patterns present in the listing and cites their sources."""
from __future__ import annotations

from rentinel.agents.base import Agent, Context
from rentinel.models import Evidence, Signal
from rentinel.retrieval import PatternRetriever


class ScamPatternAgent(Agent):
    name = "scam_patterns"

    def __init__(self, retriever: PatternRetriever | None = None):
        self._retriever = retriever

    def run(self, ctx: Context) -> Signal:
        retriever = self._retriever or PatternRetriever(ctx.kb)
        matches = retriever.match(ctx.text)
        keep = 1.0
        evidence = []
        for m in matches:
            keep *= 1 - m.pattern.severity * m.strength
            evidence.append(Evidence(
                text=f"{m.pattern.title}. {m.pattern.explanation}",
                source=m.pattern.sources[0] if m.pattern.sources else None,
                excerpt=m.sentence[:240],
            ))
        confidence = 1.0 if len(ctx.text) >= 80 else 0.6
        return Signal(agent=self.name, risk=round(1 - keep, 4), confidence=confidence, evidence=evidence)
