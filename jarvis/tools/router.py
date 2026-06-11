from dataclasses import dataclass
from enum import Enum
import re


class ToolAction(str, Enum):
    CHAT = "CHAT"
    MEMORY_RETRIEVAL = "MEMORY_RETRIEVAL"
    RESEARCH = "RESEARCH"
    HANDOFF_GENERATION = "HANDOFF_GENERATION"
    SAVE_RESEARCH = "SAVE_RESEARCH"


@dataclass(frozen=True)
class ToolRoute:
    actions: tuple[ToolAction, ...]
    model_purpose: str

    def uses(self, action: ToolAction) -> bool:
        return action in self.actions


class ToolRouter:
    research_terms = ("research", "latest", "news", "today", "current", "look up", "web", "search")
    handoff_terms = ("codex brief", "implementation brief", "codex handoff", "handoff")
    save_research_terms = ("save that research", "save this research", "store that research", "store this research")

    def route(self, user_request: str, project_id: int | None = None) -> ToolRoute:
        text = self._normalize(user_request)
        actions: list[ToolAction] = []

        if self._contains_any(text, self.save_research_terms):
            return ToolRoute((ToolAction.SAVE_RESEARCH,), "chat")

        if self._contains_any(text, self.handoff_terms):
            actions.extend((ToolAction.HANDOFF_GENERATION, ToolAction.MEMORY_RETRIEVAL, ToolAction.RESEARCH))
            return ToolRoute(tuple(dict.fromkeys(actions)), "research")

        actions.append(ToolAction.CHAT)
        if project_id is not None:
            actions.append(ToolAction.MEMORY_RETRIEVAL)
        if self._contains_any(text, self.research_terms):
            actions.append(ToolAction.RESEARCH)

        model_purpose = "research" if ToolAction.RESEARCH in actions else "chat"
        return ToolRoute(tuple(dict.fromkeys(actions)), model_purpose)

    def _normalize(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _contains_any(self, value: str, terms: tuple[str, ...]) -> bool:
        return any(term in value for term in terms)
