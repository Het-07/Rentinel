"""Small, dependency-free text helpers shared by agents."""
from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[a-z0-9$]+(?:[-'][a-z0-9]+)*")

STOPWORDS = frozenset(
    "a an and are as at be but by for from has have i if in is it its me my of on or our so "
    "that the their them then there this to us was we were will with you your".split()
)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if s and s.strip()]


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    toks = _TOKEN.findall((text or "").lower())
    return [t for t in toks if not (drop_stopwords and t in STOPWORDS)]


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
