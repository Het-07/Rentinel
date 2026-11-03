"""Turns firewall findings into a fraud signal: honest landlords don't hide text or address AIs."""
from __future__ import annotations

from rentinel.agents.base import Agent, Context
from rentinel.firewall import find_instructions
from rentinel.models import Evidence, Signal

# Risk contributed by each finding kind. Compatibility characters (e.g. "m²", "½ bath") are
# common in genuine listings, so they are reported but carry no risk.
KIND_RISK = {
    "ai_instruction": 0.90,
    "hidden_html": 0.40,
    "homoglyph": 0.55,
    "zero_width": 0.40,
    "bidi_control": 0.50,
    "compat_chars": 0.0,
}

EXPLAIN = {
    "ai_instruction": "The listing contains instructions aimed at automated reviewers, such as telling an AI to mark it safe.",
    "hidden_html": "The page hides text from human readers.",
    "homoglyph": "Look-alike letters from other alphabets are mixed into words, a trick used to dodge filters.",
    "zero_width": "Invisible characters are inserted into the text, a trick used to dodge keyword filters.",
    "bidi_control": "Text-direction control characters are used to disguise what the text says.",
}


class FirewallAgent(Agent):
    name = "firewall"

    def run(self, ctx: Context) -> Signal:
        fw = ctx.firewall
        keep = 1.0
        scored: list[tuple[float, Evidence]] = []
        seen = set()
        for f in fw.findings:
            risk = KIND_RISK.get(f.kind, 0.2)
            if f.kind == "hidden_html" and find_instructions(fw.hidden_text):
                risk = 0.95
            if risk <= 0 or f.kind in seen:
                continue
            seen.add(f.kind)
            keep *= 1 - risk
            scored.append((risk, Evidence(text=EXPLAIN.get(f.kind, f.detail), excerpt=f.excerpt or f.detail)))
        evidence = [e for _, e in sorted(scored, key=lambda x: x[0], reverse=True)]
        return Signal(agent=self.name, risk=round(1 - keep, 4), confidence=1.0, evidence=evidence)
