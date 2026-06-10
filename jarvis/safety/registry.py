from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


@dataclass(frozen=True)
class ActionDescriptor:
    name: str
    description: str
    risk_level: RiskLevel
    requires_confirmation: bool


class SafetyRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, ActionDescriptor] = {}

    def register(self, action: ActionDescriptor) -> None:
        self._actions[action.name] = action

    def get(self, name: str) -> ActionDescriptor | None:
        return self._actions.get(name)

    def list_actions(self) -> list[ActionDescriptor]:
        return list(self._actions.values())


safety_registry = SafetyRegistry()
safety_registry.register(
    ActionDescriptor(
        name="generate_codex_handoff",
        description="Create a structured implementation brief for Codex without executing code.",
        risk_level=RiskLevel.low,
        requires_confirmation=False,
    )
)
