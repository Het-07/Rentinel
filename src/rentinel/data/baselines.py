"""Official market baselines (asking rent by CMA and bedroom count)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Baseline:
    cma: str
    bedrooms: int
    asking_rent: float
    period: str
    source: str


class BaselineTable:
    def __init__(self, rows: list[Baseline]):
        self._rows = {(r.cma.lower(), r.bedrooms): r for r in rows}

    @classmethod
    def from_csv(cls, path: str | Path) -> "BaselineTable":
        lines = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
        rows = [
            Baseline(r["cma"].strip(), int(r["bedrooms"]), float(r["asking_rent"]), r.get("period", ""), r.get("source", ""))
            for r in csv.DictReader(lines)
        ]
        return cls(rows)

    def get(self, cma: str | None, bedrooms: int | None) -> Baseline | None:
        if cma is None or bedrooms is None:
            return None
        return self._rows.get((cma.lower(), min(bedrooms, 3)))  # 3 = "3 bedrooms or more"

    @property
    def as_of(self) -> str:
        periods = sorted({r.period for r in self._rows.values()})
        return periods[-1] if periods else "unknown"

    @property
    def is_sample(self) -> bool:
        return any(r.source == "sample" for r in self._rows.values())
