"""Tunable settings. Everything can be overridden with RENTINEL_* environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent


def _env(name: str, default: str) -> str:
    return os.getenv(f"RENTINEL_{name}", default)


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: _env("DB_PATH", "rentinel.db"))
    baselines_csv: str = field(
        default_factory=lambda: _env("BASELINES_CSV", str(PACKAGE_DIR / "data" / "rent_baselines.sample.csv"))
    )
    knowledge_path: str = field(
        default_factory=lambda: _env("KNOWLEDGE_PATH", str(PACKAGE_DIR / "knowledge" / "scam_patterns.yaml"))
    )
    # Verdict thresholds on the combined risk score.
    medium_threshold: float = float(_env("MEDIUM_THRESHOLD", "0.30"))
    high_threshold: float = float(_env("HIGH_THRESHOLD", "0.60"))
    # Per-agent weights in the combined score (see orchestrator._combine).
    weights: dict[str, float] = field(default_factory=lambda: {
        "firewall": 0.90,
        "scam_patterns": 0.85,
        "price": 0.65,
        "images": 0.85,
        "consistency": 0.55,
    })
    # Image reuse: max Hamming distance between perceptual hashes to call two photos "the same".
    image_hash_distance: int = int(_env("IMAGE_HASH_DISTANCE", "8"))
    # Price: local comparables needed before they replace the official baseline.
    min_local_comparables: int = int(_env("MIN_LOCAL_COMPARABLES", "10"))
    # Optional LLM (any OpenAI-compatible endpoint, e.g. Ollama at http://localhost:11434/v1).
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", ""))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "llama3.2:3b"))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", "not-needed"))
