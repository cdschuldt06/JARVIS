import re
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from jarvis.database.models import ConversationMessage
from jarvis.handoffs.service import HandoffService
from jarvis.llm import OpenAIClient
from jarvis.memory.retrieval import MemoryRetrievalService, RetrievedMemory
from jarvis.memory.service import MemoryService
from jarvis.repositories.service import RepositoryService
from jarvis.research.service import ResearchService
from jarvis.tools.router import ToolAction, ToolRouter


SYSTEM_PROMPT = """You are Jarvis, a persistent personal AI operating system.
You are one unified assistant across chat, memory, research, and implementation briefs.
Use retrieved context when it is relevant. Do not invent memory or repository components that are not present.
Do not expose retrieved context mechanically. Only surface repository, project, memory, task, decision, or research context when it directly helps answer the user's request.
When repository context is available, treat it as the current implementation and keep it separate from project memory, decisions, research, and future plans.
For repository summaries or architecture questions, generate the architecture summary from Current Repository Implementation first. Do not blend future plans, research, tasks, or decisions into the architecture summary. If they are relevant, place them only in clearly labeled sections such as Project Memory / Decisions or Research / Future Plans.
For repository risk analysis, identify current repository risks from Current Repository Implementation first. Examples include missing usage tracking, missing authentication, SQLite limits, migration concerns, repository indexing limits, tool routing complexity, and lack of automated tests. Research-based or planned-feature risks must appear only under a separate "Future Feature Risks" section, and must not be presented as current repository risks.
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
    repository_retrieved: bool = False
    memory_counts: dict[str, int] | None = None
    repository_context: dict[str, object] | None = None
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
        self.repositories = RepositoryService(db)
        self.research = ResearchService(db)
        self.handoffs = HandoffService(db)
        self.router = ToolRouter()
        self.llm = llm or OpenAIClient(db)

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
                    research_result = self.research.run_research(user_message, project_id, include_project_context=True)
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
                result = self.research.run_research(user_message, project_id, include_project_context=route.uses(ToolAction.MEMORY_RETRIEVAL))
                response_text = self._render_research_response(str(result["summary"]), result["sources"], retrieved, user_message)
                activity = ToolActivity(
                    actions=[action.value for action in route.actions],
                    model=str(result["model"]),
                    memory_retrieved=retrieved is not None,
                    research_performed=True,
                    memory_counts=self._memory_counts(retrieved),
                    repository_retrieved=route.uses(ToolAction.REPOSITORY_RETRIEVAL),
                    repository_context=self._repository_context(retrieved),
                    sources=list(result["sources"]),
                )
            self.memory.add_message("assistant", response_text, conversation_id=user_record.conversation_id, project_id=project_id)
            return UnifiedAssistantResult(user_record.conversation_id, response_text, activity)

        response_text = self._run_chat(user_record.conversation_id, retrieved, project_id)
        if retrieved is not None:
            response_text = self._append_relevant_context(response_text, retrieved, user_message)
        activity = ToolActivity(
            actions=[action.value for action in route.actions],
            model=self.llm.model,
            memory_retrieved=retrieved is not None,
            repository_retrieved=route.uses(ToolAction.REPOSITORY_RETRIEVAL),
            memory_counts=self._memory_counts(retrieved),
            repository_context=self._repository_context(retrieved),
        )
        self.memory.add_message("assistant", response_text, conversation_id=user_record.conversation_id, project_id=project_id)
        return UnifiedAssistantResult(user_record.conversation_id, response_text, activity)

    def _run_chat(self, conversation_id: str, retrieved: RetrievedMemory | None, project_id: int | None) -> str:
        context = retrieved.to_prompt_context() if retrieved is not None else "No project memory was selected for this message."
        history = self.memory.conversation_messages(conversation_id)
        guidance = self._answer_guidance(history[-1].content if history else "", retrieved)
        messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{context}\n\n{guidance}"}]
        messages.extend({"role": item.role, "content": item.content} for item in history)
        return self.llm.chat(messages, operation_type="chat", project_id=project_id, conversation_id=conversation_id)

    def _render_research_response(self, summary: str, sources: object, retrieved: RetrievedMemory | None, user_message: str) -> str:
        source_urls = [source for source in sources if isinstance(source, str)] if isinstance(sources, list) else []
        parts = [summary.strip()]
        if retrieved is not None:
            context = self._render_relevant_context(retrieved, user_message)
            if context:
                parts.append(context)
        if source_urls:
            parts.append("## Sources\n" + "\n".join(f"- {url}" for url in source_urls))
        return "\n\n".join(part for part in parts if part)

    def _append_relevant_context(self, response_text: str, retrieved: RetrievedMemory, user_message: str) -> str:
        context = self._render_relevant_context(retrieved, user_message)
        if not context:
            return response_text
        return f"{response_text.strip()}\n\n{context}"

    def _render_relevant_context(self, retrieved: RetrievedMemory, user_message: str) -> str:
        mode = self._visible_context_mode(user_message)
        sections = []
        if mode["repository"] and retrieved.repository_knowledge:
            sections.append("## Current Repository Implementation\n" + "\n".join(f"- {item.file_path}: {item.summary}" for item in retrieved.repository_knowledge))
        if mode["project"] and retrieved.decisions:
            sections.append("## Project Memory / Decisions\n" + "\n".join(f"- {item.title}: {item.details}" for item in retrieved.decisions))
        research_items = [item for item in retrieved.knowledge if item.kind == "research"]
        other_knowledge = [item for item in retrieved.knowledge if item.kind != "research"]
        if mode["project"] and research_items:
            sections.append("## Research / Future Plans\n" + "\n".join(f"- {item.title}" for item in research_items))
        if mode["project"] and other_knowledge:
            sections.append("## Other Project Knowledge\n" + "\n".join(f"- [{item.kind}] {item.title}" for item in other_knowledge))
        if mode["project"] and retrieved.tasks:
            sections.append("## Relevant Tasks\n" + "\n".join(f"- [{item.status.value}] {item.title}" for item in retrieved.tasks))
        return "\n\n".join(sections)

    def _visible_context_mode(self, user_message: str) -> dict[str, bool]:
        text = user_message.lower()
        repository_terms = (
            "architecture",
            "code",
            "component",
            "database",
            "file",
            "importer",
            "repository",
            "repo",
            "risk",
            "service",
            "structure",
        )
        project_terms = (
            "decision",
            "decisions",
            "goal",
            "memory",
            "project",
            "task",
            "tasks",
            "what should i work on",
            "work on next",
            "work on tonight",
        )
        return {
            "repository": any(term in text for term in repository_terms),
            "project": any(term in text for term in project_terms),
        }

    def _memory_counts(self, retrieved: RetrievedMemory | None) -> dict[str, int]:
        if retrieved is None:
            return {"decisions": 0, "research": 0, "tasks": 0, "repositories": 0}
        return {
            "decisions": len(retrieved.decisions),
            "research": len(retrieved.knowledge),
            "tasks": len(retrieved.tasks),
            "repositories": len(retrieved.repository_knowledge),
        }

    def _repository_context(self, retrieved: RetrievedMemory | None) -> dict[str, object] | None:
        if retrieved is None or not retrieved.repository_knowledge:
            return None
        confidence = self.repositories.confidence_for_items(retrieved.repository_knowledge)
        return {
            "files_used": confidence.files_used,
            "knowledge_items_used": confidence.knowledge_items_used,
            "last_indexed_at": confidence.last_indexed_at.isoformat() if confidence.last_indexed_at else None,
            "confidence": confidence.confidence,
        }

    def _answer_guidance(self, user_message: str, retrieved: RetrievedMemory | None) -> str:
        if retrieved is None or not retrieved.repository_knowledge:
            return "Answer guidance: respond normally using available context."
        lowered = user_message.lower()
        risk_terms = ("risk", "risks", "concern", "concerns", "weakness", "weaknesses", "gap", "gaps")
        if any(term in lowered for term in risk_terms):
            return (
                "Answer guidance for repository risk analysis:\n"
                "- Use a section titled \"Current Repository Risks\" first.\n"
                "- Base Current Repository Risks on Current Repository Implementation only.\n"
                "- Prioritize existing architecture, code, persistence, routing, tests, auth, migrations, and indexing limitations.\n"
                "- Use Project Memory / Decisions only as supporting context, clearly labeled.\n"
                "- Use Research / Future Plans only after current risks are identified.\n"
                "- Put research-based or planned-feature concerns only under \"Future Feature Risks\".\n"
                "- Do not present future feature risks as current repository risks."
            )
        return (
            "Answer guidance for repository-aware answers:\n"
            "- Lead with Current Repository Implementation when summarizing architecture or code.\n"
            "- Keep Project Memory / Decisions and Research / Future Plans in separate labeled sections when relevant."
        )

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
