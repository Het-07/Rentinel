from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from rentinel.data.baselines import BaselineTable
from rentinel.models import FirewallReport, Listing, Signal
from rentinel.retrieval import KnowledgeBase
from rentinel.config import Settings
from rentinel.store import Store


@dataclass
class Context:
    """What an agent may read. `title`/`description` are the firewall-sanitized versions."""
    listing: Listing
    title: str
    description: str
    firewall: FirewallReport
    settings: Settings
    store: Store
    baselines: BaselineTable
    kb: KnowledgeBase
    scratch: dict = field(default_factory=dict)  # per-check cache shared by run() and after_check()

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}".strip()


class Agent(ABC):
    name: str = "agent"

    @abstractmethod
    def run(self, ctx: Context) -> Signal:
        ...

    def after_check(self, ctx: Context) -> None:
        """Optional hook to record what was seen (the data flywheel)."""
