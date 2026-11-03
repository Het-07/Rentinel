"""Core data contracts shared by every agent, the orchestrator and the API."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Listing(BaseModel):
    """A rental listing as the user sees it. Every text field is UNTRUSTED input."""

    listing_id: str = Field(default="adhoc", description="Caller's id for the listing")
    title: str = ""
    description: str = ""
    price: Optional[float] = Field(default=None, description="Monthly rent in CAD")
    bedrooms: Optional[int] = Field(default=None, description="0 = studio/bachelor")
    cma: Optional[str] = Field(default=None, description="Census metropolitan area, e.g. 'Halifax'")
    address: Optional[str] = None
    source_url: Optional[str] = None
    raw_html: Optional[str] = Field(default=None, description="Listing HTML, used to find hidden text")
    images_b64: list[str] = Field(default_factory=list, description="Base64-encoded listing photos")
    image_paths: list[str] = Field(default_factory=list, description="Local photo paths (eval/dev)")


class Evidence(BaseModel):
    text: str
    source: Optional[str] = None      # where the rule or data came from (URL or dataset)
    excerpt: Optional[str] = None     # the part of the listing that triggered it


class Signal(BaseModel):
    agent: str
    risk: float = Field(ge=0, le=1, description="0 = no fraud signal, 1 = certain fraud signal")
    confidence: float = Field(ge=0, le=1, description="How much data the agent had to judge")
    evidence: list[Evidence] = Field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None


class FirewallFinding(BaseModel):
    kind: str          # e.g. "ai_instruction", "zero_width", "hidden_html", "bidi_control"
    detail: str
    excerpt: Optional[str] = None


class FirewallReport(BaseModel):
    findings: list[FirewallFinding] = Field(default_factory=list)
    sanitized_title: str = ""
    sanitized_description: str = ""
    hidden_text: str = ""

    @property
    def injection_detected(self) -> bool:
        return any(f.kind in {"ai_instruction", "hidden_html"} for f in self.findings)


class RiskLabel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Verdict(BaseModel):
    listing_id: str
    risk_score: float
    label: RiskLabel
    summary: str
    signals: list[Signal]
    firewall: FirewallReport
    data_as_of: dict[str, str] = Field(default_factory=dict)
    latency_ms: float = 0.0
