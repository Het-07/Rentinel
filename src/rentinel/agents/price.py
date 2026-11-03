"""
Price-anomaly agent: is the rent implausibly low for this market?

Reference price, in order of preference:
1. local comparables from recently checked listings (robust median), once there are enough;
2. the official baseline table (Statistics Canada asking rents by CMA and bedroom count).
"""
from __future__ import annotations

import re

from rentinel.agents.base import Agent, Context
from rentinel.models import Evidence, Signal
from rentinel.store import robust_center
from rentinel.text import clip

_AMOUNT = re.compile(r"\$\s?(\d{1,2},\d{3}|\d{3,5})(?:\.\d{2})?")
_RENT_CONTEXT = re.compile(r"\b(?:rent|month|monthly|mo|mth|lease)\b", re.I)
_OTHER_FEE = re.compile(r"\b(?:parking|storage|deposit|utilities|internet|laundry|pet fee|fee)\b", re.I)


def rent_amounts_in_text(text: str) -> list[float]:
    """Dollar amounts that look like monthly rent (skips small fees and deposits mentioned nearby)."""
    out = []
    for m in _AMOUNT.finditer(text or ""):
        value = float(m.group(1).replace(",", ""))
        before = re.split(r"[.!?\n]", text[max(0, m.start() - 30): m.start()])[-1]
        after = re.split(r"[.!?\n]", text[m.end(): m.end() + 20])[0]
        if value < 400 or _OTHER_FEE.search(before + " " + after):
            continue
        if _RENT_CONTEXT.search(before + " " + after) or value >= 700:
            out.append(value)
    return out


def price_from_text(text: str) -> float | None:
    amounts = rent_amounts_in_text(text)
    return amounts[0] if amounts else None


# Rent at or above 80% of the reference carries no risk; risk reaches 1.0 at 45% of the reference.
SAFE_RATIO = 0.80
FULL_RISK_RATIO = 0.45



def bedroom_label(n: int) -> str:
    return "studio" if n == 0 else ("3+ bedroom" if n >= 3 else f"{n}-bedroom")


class PriceAgent(Agent):
    name = "price"

    def _reference(self, ctx: Context) -> tuple[float, str, str, float] | None:
        """Returns (reference_rent, description, source, confidence)."""
        lst = ctx.listing
        comps = ctx.store.comparables(lst.cma, lst.bedrooms, lst.listing_id)
        if len(comps) >= ctx.settings.min_local_comparables:
            med, _ = robust_center(comps)
            return med, f"median of {len(comps)} recent comparable listings", "Rentinel comparables index", 1.0
        base = ctx.baselines.get(lst.cma, lst.bedrooms)
        if base:
            label = "illustrative sample baseline" if base.source == "sample" else f"average asking rent ({base.period})"
            return base.asking_rent, label, base.source, 0.85
        return None

    def run(self, ctx: Context) -> Signal:
        lst = ctx.listing
        price = lst.price if lst.price is not None else price_from_text(ctx.text)
        if price is None or lst.cma is None or lst.bedrooms is None:
            return Signal(agent=self.name, risk=0.0, confidence=0.0,
                          evidence=[Evidence(text="Not enough information (price, city, bedrooms) to compare rent.")])
        ref = self._reference(ctx)
        if ref is None:
            return Signal(agent=self.name, risk=0.0, confidence=0.0,
                          evidence=[Evidence(text=f"No rent baseline available for {lst.cma}.")])
        reference, how, source, conf = ref
        ratio = price / reference
        risk = clip((SAFE_RATIO - ratio) / (SAFE_RATIO - FULL_RISK_RATIO))
        pct = (1 - ratio) * 100
        if pct > 0:
            msg = (f"Asking ${price:,.0f}/month is {pct:.0f}% below the typical ${reference:,.0f} for a "
                   f"{bedroom_label(lst.bedrooms)} in {lst.cma} ({how}).")
        else:
            msg = f"Asking ${price:,.0f}/month is in line with or above the typical ${reference:,.0f} ({how})."
        return Signal(agent=self.name, risk=round(risk, 4), confidence=conf,
                      evidence=[Evidence(text=msg, source=source)])

    def after_check(self, ctx: Context) -> None:
        lst = ctx.listing
        ctx.store.add_observation(lst.listing_id, lst.cma, lst.bedrooms, lst.price, lst.address)
