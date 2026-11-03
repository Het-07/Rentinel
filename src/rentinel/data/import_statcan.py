"""
Convert Statistics Canada table 46-10-0092-01 (Quarterly Rent Statistics, full-table CSV download)
into Rentinel's baseline format.

    python -m rentinel.data.import_statcan 46100092.csv -o src/rentinel/data/rent_baselines.csv
    export RENTINEL_BASELINES_CSV=src/rentinel/data/rent_baselines.csv

StatCan full-table CSVs share a standard layout: REF_DATE, GEO, DGUID, one column per table
dimension, then UOM ... VALUE, STATUS, SYMBOL, TERMINATED, DECIMALS. This script finds the
unit-type dimension by its values, keeps the latest quarter per city and bedroom count, and prints
anything it could not map so you can check it.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

SOURCE = "Statistics Canada, table 46-10-0092-01"
STANDARD_COLS = {"REF_DATE", "GEO", "DGUID", "UOM", "UOM_ID", "SCALAR_FACTOR", "SCALAR_ID", "VECTOR",
                 "COORDINATE", "VALUE", "STATUS", "SYMBOL", "TERMINATED", "DECIMALS"}


def bedrooms_from_unit_type(text: str) -> int | None:
    t = text.lower()
    if "total" in t or "all " in t or re.search(r"\broom\b", t) and "bedroom" not in t:
        return None  # totals and single rooms in shared units are not comparable
    if "bachelor" in t or "studio" in t:
        return 0
    m = re.search(r"(\d)\s*(?:\+|or more)?\s*-?\s*bedroom", t) or re.search(r"(one|two|three)\s*-?\s*bedroom", t)
    if not m:
        return None
    n = {"one": 1, "two": 2, "three": 3}.get(m.group(1), None) or int(m.group(1))
    return min(n, 3)


def cma_from_geo(geo: str) -> str | None:
    if re.search(r"\bpart\b", geo, re.I) or geo.strip().lower() == "canada":
        return None  # e.g. "Ottawa - Gatineau, Ontario part": skip the partial geographies
    name = geo.split(",")[0]
    name = re.sub(r"\((?:CMA|CA)\)", "", name).strip()
    return name.split(" - ")[0].strip() or None


def _bedroom_column(rows: list[dict], columns: list[str]) -> str:
    candidates = [c for c in columns if c not in STANDARD_COLS]
    best, best_hits = None, -1
    for c in candidates:
        hits = sum(1 for r in rows[:5000] if bedrooms_from_unit_type(r.get(c, "") or "") is not None)
        if hits > best_hits:
            best, best_hits = c, hits
    if not best or best_hits == 0:
        raise SystemExit(f"Could not find a unit-type column among: {candidates}")
    return best


def convert(src: Path) -> tuple[list[dict], dict[str, int]]:
    with src.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        rows = list(reader)
    unit_col = _bedroom_column(rows, columns)
    skipped: dict[str, int] = defaultdict(int)
    latest: dict[tuple[str, int], tuple[str, float, bool]] = {}
    for r in rows:
        value = (r.get("VALUE") or "").strip()
        beds = bedrooms_from_unit_type(r.get(unit_col, ""))
        cma = cma_from_geo(r.get("GEO", ""))
        if not value or beds is None or cma is None:
            skipped[r.get(unit_col, "?")] += beds is None
            continue
        is_apartment = "apartment" in r.get(unit_col, "").lower()
        key = (cma, beds)
        cur = latest.get(key)
        ref = r.get("REF_DATE", "")
        # Newest quarter wins; within a quarter prefer apartments (most rental listings).
        if cur is None or ref > cur[0] or (ref == cur[0] and is_apartment and not cur[2]):
            latest[key] = (ref, float(value), is_apartment)
    out = [{"cma": cma, "bedrooms": beds, "asking_rent": round(v), "period": ref, "source": SOURCE}
           for (cma, beds), (ref, v, _) in sorted(latest.items())]
    return out, {k: v for k, v in skipped.items() if v}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("csv", type=Path, help="StatCan full-table CSV (e.g. 46100092.csv)")
    ap.add_argument("-o", "--out", type=Path, default=Path("rent_baselines.csv"))
    args = ap.parse_args(argv)
    rows, skipped = convert(args.csv)
    if not rows:
        raise SystemExit("No rows converted. Check that this is table 46-10-0092-01.")
    with args.out.open("w", encoding="utf-8", newline="") as f:
        f.write(f"# Converted from {SOURCE}. Latest quarter per city and bedroom count.\n")
        w = csv.DictWriter(f, fieldnames=["cma", "bedrooms", "asking_rent", "period", "source"])
        w.writeheader()
        w.writerows(rows)
    cities = sorted({r["cma"] for r in rows})
    print(f"Wrote {len(rows)} baselines for {len(cities)} cities to {args.out}", file=sys.stderr)
    for r in rows:
        if r["cma"] in ("Halifax", "Moncton", "Toronto"):
            print(f"  {r['cma']:<8} {r['bedrooms']} bed: ${r['asking_rent']:,} ({r['period']})", file=sys.stderr)
    if skipped:
        print("Unit types not used (totals, rooms, or unrecognized):", file=sys.stderr)
        for k, n in sorted(skipped.items()):
            print(f"  {k!r}: {n} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
