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
        project_goals = project.goals if project else "No explicit project goals stored yet."
        project_description = project.description if project else "No project description stored yet."
        decision_lines = "\n".join(f"- {d.title}: {d.details} Reasoning: {d.reasoning}" for d in decisions) or "- None recorded."
        task_lines = "\n".join(f"- [{t.status.value}] {t.title} ({t.priority.value}, assigned to {t.assigned_agent})" for t in tasks) or "- None recorded."
        research_lines = "\n".join(f"- {item.title}: {item.body}" for item in research) or "- None recorded."

        return f"""# Codex Implementation Brief

## Project
{project_name}

## Goal
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
