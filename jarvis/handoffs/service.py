import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.database.models import CodexHandoff, Decision, KnowledgeItem, Project, Task
from jarvis.memory.service import MemoryService


class HandoffService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.memory = MemoryService(db)

    def list_handoffs(self) -> list[CodexHandoff]:
        return self.db.scalars(select(CodexHandoff).order_by(CodexHandoff.created_at.desc())).all()

    def create_handoff(self, user_request: str, project_id: int | None = None) -> CodexHandoff:
        project = self.memory.get_project(project_id)
        decisions = self._project_decisions(project_id)
        tasks = self._project_tasks(project_id)
        research = self._project_research(project_id)
        brief = self._render_brief(user_request, project, decisions, tasks, research)
        handoff = CodexHandoff(project_id=project_id, user_request=user_request, brief=brief)
        self.db.add(handoff)
        self.db.commit()
        self.db.refresh(handoff)
        return handoff

    def _project_decisions(self, project_id: int | None) -> list[Decision]:
        stmt = select(Decision)
        if project_id is not None:
            stmt = stmt.where(Decision.project_id == project_id)
        return self.db.scalars(stmt.order_by(Decision.created_at.desc())).all()

    def _project_tasks(self, project_id: int | None) -> list[Task]:
        stmt = select(Task)
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        return self.db.scalars(stmt.order_by(Task.created_at.desc())).all()

    def _project_research(self, project_id: int | None) -> list[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(KnowledgeItem.kind == "research")
        if project_id is not None:
            stmt = stmt.where(KnowledgeItem.project_id == project_id)
        return self.db.scalars(stmt.order_by(KnowledgeItem.created_at.desc())).all()

    def _render_brief(self, user_request: str, project: Project | None, decisions: list[Decision], tasks: list[Task], research: list[KnowledgeItem]) -> str:
        project_name = project.name if project else "Unspecified project"
        goal = self._goal_from_request(user_request)
        project_goals = project.goals if project else "No explicit project goals stored yet."
        project_description = project.description if project else "No project description stored yet."
        decision_lines = "\n".join(f"- {d.title}: {d.details} Reasoning: {d.reasoning}" for d in decisions) or "- None recorded."
        task_lines = "\n".join(f"- [{t.status.value}] {t.title} ({t.priority.value}, assigned to {t.assigned_agent})" for t in tasks) or "- None recorded."
        research_lines = "\n".join(self._render_research_item(item) for item in research) or "- None recorded."

        return f"""# Codex Implementation Brief

## Project
{project_name}

## Goal
{goal}

## Project Context
{project_goals}

## Background
{project_description}

## Requirements
{task_lines}

## Known Decisions
{decision_lines}

## Known Research
{research_lines}

## Constraints
- Jarvis is the planner and memory layer.
- Codex is the builder.
- Do not add high-risk actions without explicit safety registration and confirmation gates.
- Preserve project memory, decisions, and task context.

## Implementation Request
{user_request}

## Open Questions
- Are there any missing acceptance criteria Codex should clarify before implementation?
- Are any tasks blocked by credentials, external services, or user approval?
"""

    def _goal_from_request(self, user_request: str) -> str:
        request = " ".join(user_request.strip().split())
        if not request:
            return user_request

        lowered = request.lower()
        prefixes = (
            "create an implementation plan for ",
            "create a plan for ",
            "create implementation plan for ",
            "generate an implementation plan for ",
            "generate a plan for ",
            "make an implementation plan for ",
            "implement ",
            "add ",
            "build ",
            "create ",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                goal = request[len(prefix) :].strip()
                return self._sentence_case_goal(goal) if goal else request
        return self._ensure_period(request)

    def _sentence_case_goal(self, goal: str) -> str:
        goal = goal.strip()
        if not goal:
            return goal
        replacements = {
            "adding ": "add ",
            "building ": "build ",
            "creating ": "create ",
            "implementing ": "implement ",
            "updating ": "update ",
        }
        lowered = goal.lower()
        for source, target in replacements.items():
            if lowered.startswith(source):
                goal = f"{target}{goal[len(source):]}"
                break
        return self._ensure_period(goal[0].upper() + goal[1:])

    def _ensure_period(self, text: str) -> str:
        text = text.strip()
        if not text:
            return text
        return text if text[-1] in ".!?" else f"{text}."

    def _render_research_item(self, item: KnowledgeItem) -> str:
        takeaways = self._research_takeaways(item.body)
        sources = self._research_sources(item.source)
        lines = [f"- {item.title}"]
        lines.extend(f"  - {takeaway}" for takeaway in takeaways)
        if sources:
            lines.append(f"  - Sources: {', '.join(sources)}")
        rendered = "\n".join(lines)
        if len(rendered) <= 800:
            return rendered
        return f"{rendered[:797].rstrip()}..."

    def _research_takeaways(self, body: str) -> list[str]:
        sentences = self._research_sentences(body)
        implementation_terms = (
            "api",
            "backend",
            "browser",
            "fallback",
            "feature",
            "implement",
            "integration",
            "prototype",
            "speech",
            "start",
            "support",
            "use",
        )
        selected: list[str] = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(term in lowered for term in implementation_terms):
                selected.append(self._ensure_period(sentence))
            if len(selected) == 4:
                break
        if not selected:
            selected = [self._ensure_period(sentence) for sentence in sentences[:4]]
        return selected

    def _research_sentences(self, body: str) -> list[str]:
        cleaned_lines = []
        skip_prefixes = ("concise summary", "key findings", "recommendation", "summary")
        for line in body.splitlines():
            stripped = line.strip().lstrip("-*#0123456789. ")
            if not stripped:
                continue
            if stripped.lower().rstrip(":") in skip_prefixes:
                continue
            cleaned_lines.append(stripped)
        cleaned = " ".join(cleaned_lines)
        parts = re.split(r"(?<=[.!?])\s+", cleaned)
        return [part.strip() for part in parts if len(part.strip()) > 20]

    def _research_sources(self, source: str) -> list[str]:
        if not source:
            return []
        try:
            parsed = json.loads(source)
        except json.JSONDecodeError:
            return []
        urls = parsed.get("urls") if isinstance(parsed, dict) else None
        if not isinstance(urls, list):
            return []
        return [url for url in urls if isinstance(url, str) and url.startswith(("http://", "https://"))][:4]
