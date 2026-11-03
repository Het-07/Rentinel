"""
Local store for the data flywheel: every checked listing adds its asking rent and photo hashes,
so price comparables and duplicate-photo detection improve with use. Stores no personal data.
"""
from __future__ import annotations

import sqlite3
import statistics
import threading
import time
from dataclasses import dataclass

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    listing_id TEXT PRIMARY KEY, cma TEXT, bedrooms INTEGER, price REAL, address TEXT, seen_at REAL
);
CREATE INDEX IF NOT EXISTS obs_market ON observations (cma, bedrooms);
CREATE TABLE IF NOT EXISTS image_hashes (
    listing_id TEXT, phash TEXT, address TEXT, cma TEXT, price REAL, seen_at REAL,
    PRIMARY KEY (listing_id, phash)
);
"""


@dataclass
class ImageMatch:
    listing_id: str
    distance: int
    address: str | None
    cma: str | None
    price: float | None


class Store:
    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def add_observation(self, listing_id, cma, bedrooms, price, address) -> None:
        if price is None or cma is None or bedrooms is None:
            return
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?)",
                               (listing_id, cma.lower(), bedrooms, price, address, time.time()))
            self._conn.commit()

    def comparables(self, cma: str, bedrooms: int, exclude_id: str, max_age_days: int = 120) -> list[float]:
        cutoff = time.time() - max_age_days * 86400
        with self._lock:
            rows = self._conn.execute(
                "SELECT price FROM observations WHERE cma=? AND bedrooms=? AND listing_id<>? AND seen_at>=?",
                (cma.lower(), min(bedrooms, 3), exclude_id, cutoff)).fetchall()
        return [r[0] for r in rows]

    def add_image_hashes(self, listing_id, hashes: list[str], address, cma, price) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO image_hashes VALUES (?,?,?,?,?,?)",
                [(listing_id, h, address, cma, price, time.time()) for h in hashes])
            self._conn.commit()

    def similar_images(self, phash_hex: str, exclude_id: str, max_distance: int) -> list[ImageMatch]:
        """Linear scan is fine for tens of thousands of photos; swap in a BK-tree or vector index beyond that."""
        target = int(phash_hex, 16)
        with self._lock:
            rows = self._conn.execute(
                "SELECT listing_id, phash, address, cma, price FROM image_hashes WHERE listing_id<>?",
                (exclude_id,)).fetchall()
        out = []
        for lid, h, addr, cma, price in rows:
            d = bin(target ^ int(h, 16)).count("1")
            if d <= max_distance:
                out.append(ImageMatch(lid, d, addr, cma, price))
        return sorted(out, key=lambda m: m.distance)


def robust_center(values: list[float]) -> tuple[float, float]:
    """Median and scaled MAD, which ignore the occasional absurd price better than mean/std."""
    med = statistics.median(values)
    mad = statistics.median(abs(v - med) for v in values) * 1.4826
    return med, mad
