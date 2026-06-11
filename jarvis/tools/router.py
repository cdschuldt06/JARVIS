from dataclasses import dataclass
from enum import Enum
import re


class ToolAction(str, Enum):
    CHAT = "CHAT"
    MEMORY_RETRIEVAL = "MEMORY_RETRIEVAL"
    NEWS = "NEWS"
    MARKET = "MARKET"
    CODEX_TASK = "CODEX_TASK"
    CODEX_TASK_RUN_REQUEST = "CODEX_TASK_RUN_REQUEST"
    RESEARCH = "RESEARCH"
    SAVE_RESEARCH = "SAVE_RESEARCH"
    REPOSITORY_RETRIEVAL = "REPOSITORY_RETRIEVAL"


@dataclass(frozen=True)
class ToolRoute:
    actions: tuple[ToolAction, ...]
    model_purpose: str

    def uses(self, action: ToolAction) -> bool:
        return action in self.actions


class ToolRouter:
    research_terms = ("research", "latest", "current", "look up", "web", "search")
    deep_research_terms = ("deep research", "research the", "research impact", "investigate", "analyze the impact")
    news_terms = (
        "ai news",
        "headlines",
        "in the news",
        "news today",
        "top news",
        "today's news",
        "todays news",
        "what happened today",
        "what's in the news",
    )
    market_terms = (
        "aapl",
        "alphabet",
        "amazon",
        "amd",
        "amzn",
        "apple",
        "googl",
        "google",
        "market",
        "markets",
        "meta",
        "microsoft",
        "msft",
        "nvda",
        "nvidia",
        "spy",
        "qqq",
        "dia",
        "stock",
        "vix",
        "tesla",
        "tsla",
        "btc",
        "bitcoin",
        "stocks",
        "nasdaq",
        "dow",
        "s&p",
    )
    handoff_terms = ("codex brief", "implementation brief", "codex handoff", "handoff")
    save_research_terms = ("save that research", "save this research", "store that research", "store this research")
    codex_task_terms = ("create a codex task", "create codex task", "make a codex task", "add a codex task")
    codex_task_run_terms = ("run the codex task", "execute the codex task", "start the codex task")
    repository_terms = (
        "architecture",
        "code",
        "component",
        "database",
        "explain",
        "file",
        "frontend",
        "github",
        "importer",
        "repository",
        "repo",
        "risk",
        "service",
        "structure",
        "work on next",
        "work on tonight",
    )
    project_context_terms = (
        "for jarvis",
        "jarvis",
        "our project",
        "project",
        "how does this affect",
        "how does this relate",
        "relevance",
        "relevant to",
        "what should i work on",
        "work on next",
        "work on tonight",
    )

    def route(self, user_request: str, project_id: int | None = None) -> ToolRoute:
        text = self._normalize(user_request)
        actions: list[ToolAction] = []

        if self._contains_any(text, self.save_research_terms):
            return ToolRoute((ToolAction.SAVE_RESEARCH,), "chat")

        if self._contains_any(text, self.codex_task_run_terms):
            return ToolRoute((ToolAction.CODEX_TASK_RUN_REQUEST,), "chat")

        if self._contains_any(text, self.codex_task_terms) or self._contains_any(text, self.handoff_terms):
            return ToolRoute((ToolAction.CODEX_TASK,), "chat")

        if self._uses_market(text):
            return ToolRoute((ToolAction.MARKET,), "chat")

        if self._uses_news(text):
            return ToolRoute((ToolAction.NEWS,), "chat")

        uses_research = self._contains_any(text, self.research_terms) or self._contains_any(text, self.deep_research_terms)
        uses_project_context = self._contains_any(text, self.project_context_terms)

        actions.append(ToolAction.CHAT)
        if project_id is not None and (not uses_research or uses_project_context):
            actions.append(ToolAction.MEMORY_RETRIEVAL)
            if self._contains_any(text, self.repository_terms):
                actions.append(ToolAction.REPOSITORY_RETRIEVAL)
        if uses_research:
            actions.append(ToolAction.RESEARCH)

        model_purpose = "research" if ToolAction.RESEARCH in actions else "chat"
        return ToolRoute(tuple(dict.fromkeys(actions)), model_purpose)

    def _normalize(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def _contains_any(self, value: str, terms: tuple[str, ...]) -> bool:
        return any(term in value for term in terms)

    def _uses_news(self, value: str) -> bool:
        if self._contains_any(value, self.deep_research_terms):
            return False
        return self._contains_any(value, self.news_terms) or ("news" in value and "research" not in value)

    def _uses_market(self, value: str) -> bool:
        if self._contains_any(value, self.deep_research_terms):
            return False
        if self._contains_any(value, self.market_terms):
            return any(term in value for term in ("today", "doing", "happened", "market", "markets", "price", "how is", "what's", "check", "tell me about", "stock"))
        return bool(re.search(r"\b(how is|what'?s|check|tell me about)\s+[a-z0-9. -]{2,20}\b", value))
