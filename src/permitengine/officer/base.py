"""The officer's interface. Two versions: simulated rules from labels, and an LLM reading the rubric."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Ruling:
    ruling: str | None  # approve, deny, or None when the LLM officer failed
    outcome_risky: bool | None
    reason: str
    named: list = field(default_factory=list)  # {"tree_id": str, "level": int}


class Officer(Protocol):
    label: str

    def rule(self, view: dict) -> Ruling: ...
