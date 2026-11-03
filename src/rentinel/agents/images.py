"""
Image-reuse agent: are these photos already attached to a different listing?

Uses perceptual hashes (pHash), which survive resizing, recompression and light cropping, so a
scammer re-saving someone else's photos is still caught. Stolen photos usually show up under a
different address, city or price; the same address re-listed is treated as a mild signal only.
"""
from __future__ import annotations

import base64
import io

import imagehash
from PIL import Image

from rentinel.agents.base import Agent, Context
from rentinel.models import Evidence, Signal


def _norm_addr(a: str | None) -> str:
    return " ".join((a or "").lower().replace(",", " ").split())


def load_images(b64_list: list[str], paths: list[str]) -> list[Image.Image]:
    images = []
    for b in b64_list:
        try:
            images.append(Image.open(io.BytesIO(base64.b64decode(b.split(",")[-1]))))
        except Exception:
            continue
    for p in paths:
        try:
            images.append(Image.open(p))
        except Exception:
            continue
    return images


def phash_hex(img: Image.Image) -> str:
    return str(imagehash.phash(img.convert("RGB")))


class ImageReuseAgent(Agent):
    name = "images"

    def _hashes(self, ctx: Context) -> list[str]:
        if "phashes" not in ctx.scratch:
            ctx.scratch["phashes"] = [phash_hex(i) for i in load_images(ctx.listing.images_b64, ctx.listing.image_paths)]
        return ctx.scratch["phashes"]

    def run(self, ctx: Context) -> Signal:
        lst = ctx.listing
        hashes = self._hashes(ctx)
        if not hashes:
            return Signal(agent=self.name, risk=0.0, confidence=0.0,
                          evidence=[Evidence(text="No photos to check.")])
        reused_elsewhere, relisted = set(), set()
        examples = []
        for h in hashes:
            for m in ctx.store.similar_images(h, lst.listing_id, ctx.settings.image_hash_distance):
                same_place = (_norm_addr(m.address) and _norm_addr(m.address) == _norm_addr(lst.address))
                if same_place:
                    relisted.add(m.listing_id)
                else:
                    reused_elsewhere.add(h)
                    if len(examples) < 3:
                        where = m.address or m.cma or "another listing"
                        examples.append(f"photo matches listing {m.listing_id} at {where}")
                break
        share = len(reused_elsewhere) / len(hashes)
        if reused_elsewhere:
            risk = min(1.0, 0.70 + 0.30 * share)
            ev = [Evidence(text=f"{len(reused_elsewhere)} of {len(hashes)} photos already appear in a listing for a "
                                f"different address.", excerpt="; ".join(examples))]
        elif relisted:
            risk = 0.15
            ev = [Evidence(text="Photos match an earlier listing at the same address (likely a re-listing).")]
        else:
            risk = 0.0
            ev = [Evidence(text=f"None of the {len(hashes)} photos match other listings seen so far.")]
        return Signal(agent=self.name, risk=round(risk, 4), confidence=0.85, evidence=ev)

    def after_check(self, ctx: Context) -> None:
        lst = ctx.listing
        hashes = self._hashes(ctx)
        if hashes:
            ctx.store.add_image_hashes(lst.listing_id, hashes, lst.address, lst.cma, lst.price)
