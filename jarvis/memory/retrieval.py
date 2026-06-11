import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.database.models import Decision, KnowledgeItem, Project, Task


@dataclass(frozen=True)
class RetrievedMemory:
    project: Project | None
    decisions: list[Decision]
    knowledge: list[KnowledgeItem]
    tasks: list[Task]

    def to_prompt_context(self) -> str:
        sections = ["Relevant Jarvis memory:"]
        if self.project:
            sections.append(f"Project: {self.project.name}\nGoals: {self.project.goals or 'None recorded.'}\nDescription: {self.project.description or 'None recorded.'}")
        if self.decisions:
            sections.append("Decisions:\n" + "\n".join(f"- {item.title}: {item.details} Reasoning: {item.reasoning}" for item in self.decisions))
        if self.knowledge:
            sections.append("Knowledge:\n" + "\n".join(f"- [{item.kind}] {item.title}: {item.body}" for item in self.knowledge))
        if self.tasks:
            sections.append("Tasks:\n" + "\n".join(f"- [{item.status.value}] {item.title}: {item.description}" for item in self.tasks))
        if len(sections) == 1:
            sections.append("No relevant stored memory found.")
        return "\n\n".join(sections)


class MemoryRetrievalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def retrieve(self, query: str, project_id: int | None = None, limit: int = 5) -> RetrievedMemory:
        terms = self._terms(query)
        project = self.db.get(Project, project_id) if project_id is not None else None
        decisions = self._ranked(self._project_rows(select(Decision), Decision.project_id, project_id), terms, ("title", "details", "reasoning"), limit)
        knowledge = self._ranked(self._project_rows(select(KnowledgeItem), KnowledgeItem.project_id, project_id), terms, ("title", "body", "kind"), limit)
        tasks = self._ranked(self._project_rows(select(Task), Task.project_id, project_id), terms, ("title", "description", "assigned_agent", "status", "priority"), limit)
        return RetrievedMemory(project=project, decisions=decisions, knowledge=knowledge, tasks=tasks)

    def _project_rows(self, stmt, project_column, project_id: int | None):
        if project_id is not None:
            stmt = stmt.where(project_column == project_id)
        return self.db.scalars(stmt).all()

    def _ranked(self, rows: list, terms: set[str], fields: tuple[str, ...], limit: int) -> list:
        scored = []
        for row in rows:
            haystack = " ".join(str(getattr(row, field, "") or "") for field in fields).lower()
            score = sum(1 for term in terms if term in haystack)
            if score > 0 or not terms:
                scored.append((score, row))
        scored.sort(key=lambda item: (item[0], getattr(item[1], "created_at", None)), reverse=True)
        return [row for _, row in scored[:limit]]

    def _terms(self, query: str) -> set[str]:
        stop_words = {"a", "an", "and", "are", "build", "for", "how", "is", "of", "or", "the", "this", "to", "we", "what", "with"}
        return {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2 and term not in stop_words}
