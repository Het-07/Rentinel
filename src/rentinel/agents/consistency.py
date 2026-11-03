"""
Consistency agent: does the listing contradict itself, or contradict public property records?

Internal checks run offline. Property-record checks go through an `AddressDirectory`; the default
directory knows nothing (confidence 0), and the Halifax open-data directory plugs in later.
"""
from __future__ import annotations

import re
from typing import Protocol

from rentinel.agents.base import Agent, Context
from rentinel.agents.price import rent_amounts_in_text
from rentinel.models import Evidence, Signal

_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "single": 1}
_BEDS = re.compile(r"\b(\d|one|two|three|four|five|single)[\s-]*(?:bed(?:room)?s?|br|bdrm?s?)\b", re.I)
_STUDIO = re.compile(r"\b(?:studio|bachelor)\b", re.I)
_CITIES = ["halifax", "dartmouth", "bedford", "moncton", "toronto", "vancouver", "montreal", "calgary", "ottawa",
           "edmonton", "winnipeg", "fredericton", "saint john", "charlottetown", "st. john's", "quebec city"]
_CMA_ALIASES = {"halifax": {"halifax", "dartmouth", "bedford", "sackville", "clayton park", "spryfield"}}
_LOCATED = re.compile(r"\b(?:located in|apartment in|unit in|suite in|house in|condo in|place in|home in)\s+"
                      r"(?:downtown\s+|the heart of\s+)?([a-z .']{3,20})", re.I)


class AddressDirectory(Protocol):
    def lookup(self, address: str, cma: str | None) -> dict | None:
        """Return facts about the address (e.g. {'exists': True, 'building_type': 'single detached'}) or None."""


class NullDirectory:
    def lookup(self, address, cma):
        return None


class ConsistencyAgent(Agent):
    name = "consistency"

    def __init__(self, directory: AddressDirectory | None = None):
        self.directory = directory or NullDirectory()

    def run(self, ctx: Context) -> Signal:
        lst = ctx.listing
        text = ctx.text
        issues: list[tuple[float, Evidence]] = []

        if lst.bedrooms is not None:
            # Check the description on its own: titles are often generated from the structured fields.
            mentioned = {int(m) if m.isdigit() else _WORD_NUM[m.lower()] for m in _BEDS.findall(ctx.description)}
            if lst.bedrooms == 0 and mentioned:
                issues.append((0.45, Evidence(text="Listed as a studio, but the description mentions bedrooms.",
                                              excerpt=", ".join(map(str, sorted(mentioned))) + " bedroom")))
            elif lst.bedrooms > 0 and mentioned and lst.bedrooms not in mentioned:
                issues.append((0.45, Evidence(text=f"Listed as {lst.bedrooms} bedroom(s), but the description says "
                                                   f"{', '.join(map(str, sorted(mentioned)))}.")))
            elif lst.bedrooms > 0 and _STUDIO.search(text) and not mentioned:
                issues.append((0.35, Evidence(text="Listed with bedrooms, but described as a studio.")))

        amounts = rent_amounts_in_text(text)
        if lst.price and amounts and all(abs(a - lst.price) / lst.price > 0.10 for a in amounts):
            issues.append((0.50, Evidence(text=f"Price field says ${lst.price:,.0f} but the description says "
                                               f"${amounts[0]:,.0f}.")))

        if lst.cma:
            allowed = _CMA_ALIASES.get(lst.cma.lower(), {lst.cma.lower()})
            for m in _LOCATED.finditer(text):
                place = m.group(1).lower()
                city = next((c for c in _CITIES if place.startswith(c)), None)
                if city and city not in allowed:
                    issues.append((0.40, Evidence(text=f"Listing is in {lst.cma}, but the description places the unit "
                                                       f"in {city.title()}.", excerpt=m.group(0))))
                    break

        confidence = 0.6
        if lst.address:
            facts = self.directory.lookup(lst.address, lst.cma)
            if facts is not None:
                confidence = 0.9
                if facts.get("exists") is False:
                    issues.append((0.70, Evidence(text="The address was not found in municipal address records.",
                                                  source=facts.get("source"))))

        keep = 1.0
        for r, _ in issues:
            keep *= 1 - r
        return Signal(agent=self.name, risk=round(1 - keep, 4), confidence=confidence,
                      evidence=[e for _, e in issues] or [Evidence(text="No internal contradictions found.")])
