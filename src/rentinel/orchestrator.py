"""
Orchestrator: runs the firewall first, then every specialist agent in parallel, then combines
their signals into one explainable verdict.

Design rule ("decision isolation"): the verdict is computed from agent signals, never by an LLM
reading raw listing text. An optional LLM only writes the explanation, and it receives sanitized
text inside a delimited data block, so injected instructions cannot change the score.
"""
from __future__ import annotations

import asyncio
import time
from typing import Iterable

from rentinel import firewall
from rentinel.agents import ConsistencyAgent, FirewallAgent, ImageReuseAgent, PriceAgent, ScamPatternAgent
from rentinel.agents.base import Agent, Context
from rentinel.config import Settings
from rentinel.data.baselines import BaselineTable
from rentinel.models import FirewallReport, Listing, RiskLabel, Signal, Verdict
from rentinel.retrieval import KnowledgeBase
from rentinel.store import Store

AGENT_NAMES = ("firewall", "scam_patterns", "price", "images", "consistency")


class Orchestrator:
    def __init__(self, settings: Settings | None = None, store: Store | None = None,
                 agents: Iterable[Agent] | None = None, disable: Iterable[str] = (), explainer=None):
        self.settings = settings or Settings()
        self.store = store or Store(self.settings.db_path)
        self.baselines = BaselineTable.from_csv(self.settings.baselines_csv)
        self.kb = KnowledgeBase(self.settings.knowledge_path)
        self.disable = set(disable)
        all_agents = list(agents) if agents is not None else [
            FirewallAgent(), ScamPatternAgent(), PriceAgent(), ImageReuseAgent(), ConsistencyAgent()]
        self.agents = [a for a in all_agents if a.name not in self.disable]
        self.explainer = explainer

    # ---------- scoring ----------
    def _combine(self, signals: list[Signal]) -> float:
        """Noisy-OR: each agent independently 'explains' fraud with probability weight*confidence*risk."""
        keep = 1.0
        for s in signals:
            w = self.settings.weights.get(s.agent, 0.5)
            keep *= 1 - w * s.confidence * s.risk
        return round(1 - keep, 4)

    def _label(self, score: float) -> RiskLabel:
        if score >= self.settings.high_threshold:
            return RiskLabel.high
        if score >= self.settings.medium_threshold:
            return RiskLabel.medium
        return RiskLabel.low

    @staticmethod
    def _summary(label: RiskLabel, signals: list[Signal]) -> str:
        ranked = sorted((s for s in signals if s.risk > 0.05), key=lambda s: s.risk * s.confidence, reverse=True)
        if not ranked:
            return "No fraud signals found. Still view the unit in person and sign a lease before paying anything."
        reasons = [s.evidence[0].text.split(". ")[0].rstrip(".") for s in ranked[:3] if s.evidence]
        head = {"high": "High risk of fraud", "medium": "Some warning signs",
                "low": "Low risk, minor warning signs"}[label.value]
        return f"{head}: " + "; ".join(reasons) + "."

    # ---------- running ----------
    async def _run_agent(self, agent: Agent, ctx: Context) -> Signal:
        t = time.perf_counter()
        try:
            sig = await asyncio.to_thread(agent.run, ctx)
        except Exception as e:  # one failing agent must not sink the whole check
            sig = Signal(agent=agent.name, risk=0.0, confidence=0.0, error=f"{type(e).__name__}: {e}")
        sig.latency_ms = round((time.perf_counter() - t) * 1000, 2)
        return sig

    async def check(self, listing: Listing, register: bool = True) -> Verdict:
        t0 = time.perf_counter()
        if "firewall" in self.disable:
            report = FirewallReport(sanitized_title=listing.title, sanitized_description=listing.description)
        else:
            report = firewall.inspect(listing)
        ctx = Context(listing=listing, title=report.sanitized_title, description=report.sanitized_description,
                      firewall=report, settings=self.settings, store=self.store, baselines=self.baselines, kb=self.kb)

        signals = list(await asyncio.gather(*(self._run_agent(a, ctx) for a in self.agents)))
        score = self._combine(signals)
        label = self._label(score)
        summary = self._summary(label, signals)
        if self.explainer is not None:
            try:
                summary = await asyncio.to_thread(self.explainer.explain, ctx, signals, label, score) or summary
            except Exception:
                pass  # the template summary is always a safe fallback

        if register:
            for a in self.agents:
                try:
                    a.after_check(ctx)
                except Exception:
                    pass

        return Verdict(
            listing_id=listing.listing_id, risk_score=score, label=label, summary=summary, signals=signals,
            firewall=report,
            data_as_of={
                "scam_patterns": self.kb.reviewed,
                "rent_baseline": "illustrative sample" if self.baselines.is_sample else self.baselines.as_of,
            },
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )

    def check_sync(self, listing: Listing, register: bool = True) -> Verdict:
        return asyncio.run(self.check(listing, register=register))
