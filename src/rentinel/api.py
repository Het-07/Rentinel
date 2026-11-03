"""
HTTP API.

    uvicorn rentinel.api:app --reload
    curl -X POST localhost:8000/v1/check -H 'content-type: application/json' \
         -d '{"title": "2 bed downtown", "description": "...", "price": 1200, "bedrooms": 2, "cma": "Halifax"}'
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from rentinel import __version__
from rentinel.config import Settings
from rentinel.models import Listing, Verdict
from rentinel.orchestrator import Orchestrator

MAX_IMAGES = 12
MAX_TEXT = 20_000


def _build_orchestrator(settings: Settings) -> Orchestrator:
    explainer = None
    if settings.llm_base_url:
        from rentinel.llm import ChatClient, GuardedExplainer
        explainer = GuardedExplainer(ChatClient(settings))
    return Orchestrator(settings=settings, explainer=explainer)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.orchestrator = _build_orchestrator(Settings())
    yield


app = FastAPI(title="Rentinel", version=__version__, lifespan=lifespan)


_DEMO_PAGE = Path(__file__).parent / "web" / "index.html"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def demo_page() -> str:
    return _DEMO_PAGE.read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.post("/v1/check", response_model=Verdict)
async def check(listing: Listing) -> Verdict:
    if len(listing.description) + len(listing.title) + len(listing.raw_html or "") > MAX_TEXT * 5:
        raise HTTPException(413, "Listing text is too large.")
    if len(listing.images_b64) > MAX_IMAGES:
        raise HTTPException(413, f"At most {MAX_IMAGES} photos per check.")
    listing.image_paths = []  # local paths are for offline evaluation only, never from the network
    return await app.state.orchestrator.check(listing)
