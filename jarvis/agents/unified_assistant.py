import re
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from jarvis.database.models import ConversationMessage
from jarvis.handoffs.service import HandoffService
from jarvis.llm import OpenAIClient
from jarvis.memory.retrieval import MemoryRetrievalService, RetrievedMemory
from jarvis.memory.service import MemoryService
from jarvis.research.service import ResearchService
from jarvis.tools.router import ToolAction, ToolRouter


SYSTEM_PROMPT = """You are Jarvis, a persistent personal AI operating system.
You are one unified assistant across chat, memory, research, and implementation briefs.
Use retrieved project memory when it is relevant. Do not invent memory that is not present.
You do not claim to execute code, control computers, place trades, send email, or write to GitHub.
When implementation is needed, prepare context for Codex."""


@dataclass(frozen=True)
class ToolActivity:
    actions: list[str]
    model: str
    memory_retrieved: bool = False
    research_performed: bool = False
    handoff_generated: bool = False
    research_saved: bool = False
    memory_counts: dict[str, int] | None = None
    sources: list[str] | None = None


@dataclass(frozen=True)
class UnifiedAssistantResult:
    conversation_id: str
    response: str
    activity: ToolActivity


class UnifiedAssistant:
    def __init__(self, db: Session, llm: OpenAIClient | None = None) -> None:
        self.db = db
        self.memory = MemoryService(db)
        self.retrieval = MemoryRetrievalService(db)
        self.research = ResearchService(db)
        self.handoffs = HandoffService(db)
        self.router = ToolRouter()
        self.llm = llm or OpenAIClient()

    def chat(
        self,
        user_message: str,
        conversation_id: str | None = None,
        input_mode: str = "text",
        project_id: int | None = None,
    ) -> UnifiedAssistantResult:
        user_record = self.memory.add_message(
            "user",
            user_message,
            conversation_id=conversation_id,
            input_mode=input_mode,
            project_id=project_id,
        )
        route = self.router.route(user_message, project_id=project_id)

        if route.uses(ToolAction.SAVE_RESEARCH):
            response_text, saved = self._save_recent_research(user_record.conversation_id, project_id)
            activity = ToolActivity(
                actions=[action.value for action in route.actions],
                model=self.llm.model,
                research_saved=saved,
            )
            self.memory.add_message("assistant", response_text, conversation_id=user_record.conversation_id, project_id=project_id)
            return UnifiedAssistantResult(user_record.conversation_id, response_text, activity)

        if route.uses(ToolAction.HANDOFF_GENERATION):
            if project_id is None:
                response_text = "Select a Current Project before generating a Codex brief."
                activity = ToolActivity(actions=[action.value for action in route.actions], model=self.research.model)
            else:
                research_sources: list[str] = []
                if route.uses(ToolAction.RESEARCH):
                    research_result = self.research.run_research(user_message, project_id)
                    research_sources = list(research_result["sources"])
                    self.research.save_research(
                        title=f"Fresh research: {user_message[:160]}",
                        summary=str(research_result["summary"]),
                        sources=research_sources,
                        project_id=project_id,
                    )
                handoff = self.handoffs.create_handoff(user_message, project_id)
                response_text = f"Generated a Codex implementation brief for the current project.\n\n{handoff.brief}"
                activity = ToolActivity(
                    actions=[action.value for action in route.actions],
                    model=self.research.model if route.uses(ToolAction.RESEARCH) else "deterministic",
                    memory_retrieved=True,
                    research_performed=route.uses(ToolAction.RESEARCH),
                    handoff_generated=True,
                    research_saved=route.uses(ToolAction.RESEARCH),
                    sources=research_sources,
                )
            self.memory.add_message("assistant", response_text, conversation_id=user_record.conversation_id, project_id=project_id)
            return UnifiedAssistantResult(user_record.conversation_id, response_text, activity)

        retrieved = self.retrieval.retrieve(user_message, project_id=project_id) if route.uses(ToolAction.MEMORY_RETRIEVAL) else None

        if route.uses(ToolAction.RESEARCH):
            if project_id is None:
                response_text = "Select a Current Project before Jarvis runs research. Typed chat still works without a project."
                activity = ToolActivity(actions=[action.value for action in route.actions], model=self.research.model)
            else:
                result = self.research.run_research(user_message, project_id)
                response_text = self._render_research_response(str(result["summary"]), result["sources"], retrieved)
                activity = ToolActivity(
                    actions=[action.value for action in route.actions],
                    model=str(result["model"]),
                    memory_retrieved=retrieved is not None,
                    research_performed=True,
                    memory_counts=self._memory_counts(retrieved),
                    sources=list(result["sources"]),
                )
            self.memory.add_message("assistant", response_text, conversation_id=user_record.conversation_id, project_id=project_id)
            return UnifiedAssistantResult(user_record.conversation_id, response_text, activity)

        response_text = self._run_chat(user_record.conversation_id, retrieved)
        if retrieved is not None:
            response_text = self._append_memory_highlights(response_text, retrieved)
        activity = ToolActivity(
            actions=[action.value for action in route.actions],
            model=self.llm.model,
            memory_retrieved=retrieved is not None,
            memory_counts=self._memory_counts(retrieved),
        )
        self.memory.add_message("assistant", response_text, conversation_id=user_record.conversation_id, project_id=project_id)
        return UnifiedAssistantResult(user_record.conversation_id, response_text, activity)

    def _run_chat(self, conversation_id: str, retrieved: RetrievedMemory | None) -> str:
        context = retrieved.to_prompt_context() if retrieved is not None else "No project memory was selected for this message."
        history = self.memory.conversation_messages(conversation_id)
        messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{context}"}]
        messages.extend({"role": item.role, "content": item.content} for item in history)
        return self.llm.chat(messages)

    def _render_research_response(self, summary: str, sources: object, retrieved: RetrievedMemory | None) -> str:
        source_urls = [source for source in sources if isinstance(source, str)] if isinstance(sources, list) else []
        parts = [summary.strip()]
        if retrieved is not None:
            memory = self._render_memory_highlights(retrieved)
            if memory:
                parts.append(memory)
        if source_urls:
            parts.append("## Sources\n" + "\n".join(f"- {url}" for url in source_urls))
        return "\n\n".join(part for part in parts if part)

    def _append_memory_highlights(self, response_text: str, retrieved: RetrievedMemory) -> str:
        memory = self._render_memory_highlights(retrieved)
        if not memory:
            return response_text
        return f"{response_text.strip()}\n\n{memory}"

    def _render_memory_highlights(self, retrieved: RetrievedMemory) -> str:
        sections = []
        if retrieved.decisions:
            sections.append("## Relevant Decisions\n" + "\n".join(f"- {item.title}: {item.details}" for item in retrieved.decisions))
        if retrieved.knowledge:
            sections.append("## Relevant Research\n" + "\n".join(f"- {item.title}" for item in retrieved.knowledge))
        if retrieved.tasks:
            sections.append("## Relevant Tasks\n" + "\n".join(f"- [{item.status.value}] {item.title}" for item in retrieved.tasks))
        return "\n\n".join(sections)

    def _memory_counts(self, retrieved: RetrievedMemory | None) -> dict[str, int]:
        if retrieved is None:
            return {"decisions": 0, "research": 0, "tasks": 0}
        return {
            "decisions": len(retrieved.decisions),
            "research": len(retrieved.knowledge),
            "tasks": len(retrieved.tasks),
        }

    def _save_recent_research(self, conversation_id: str, project_id: int | None) -> tuple[str, bool]:
        if project_id is None:
            return "Select a Current Project before saving research.", False
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id, ConversationMessage.role == "assistant")
            .order_by(desc(ConversationMessage.created_at))
        )
        for message in self.db.scalars(stmt).all():
            urls = self._extract_urls(message.content)
            if "## Sources" in message.content or urls:
                title = self._research_title(message.content)
                self.research.save_research(title, message.content, urls, project_id)
                return f"Saved research to the current project as '{title}'.", True
        return "I do not have a recent research result to save yet.", False

    def _extract_urls(self, text: str) -> list[str]:
        urls: list[str] = []
        for url in re.findall(r"https?://[^\s)>\]]+", text):
            cleaned = url.rstrip(".,")
            if cleaned not in urls:
                urls.append(cleaned)
        return urls

    def _research_title(self, text: str) -> str:
        first_line = next((line.strip("# -") for line in text.splitlines() if line.strip()), "Saved research")
        return f"Saved research: {first_line[:80]}"
