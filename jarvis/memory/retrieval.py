import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.database.models import Decision, KnowledgeItem, Project, RepositoryKnowledge, Task
from jarvis.repositories.service import RepositoryService


@dataclass(frozen=True)
class RetrievedMemory:
    project: Project | None
    decisions: list[Decision]
    knowledge: list[KnowledgeItem]
    tasks: list[Task]
    repository_knowledge: list[RepositoryKnowledge]

    def to_prompt_context(self) -> str:
        sections = [
            "Retrieved Jarvis context:",
            (
                "Grounding rules:\n"
                "- Current Repository Implementation is indexed from the actual registered repository files.\n"
                "- Project Memory / Decisions are stored planning context, not proof that code exists.\n"
                "- Research / Future Plans may describe options or intended work, not current implementation.\n"
                "- For repository summaries or architecture answers, build the architecture summary from Current Repository Implementation only.\n"
                "- If project memory, decisions, tasks, research, or future plans are relevant, put them in dedicated labeled sections and do not blend them into the architecture summary.\n"
                "- For repository risk analysis, identify Current Repository Risks from Current Repository Implementation before using memory or research.\n"
                "- Research-based or planned-feature risks belong only in a separate Future Feature Risks section."
            ),
        ]
        if self.project:
            sections.append(f"Project Context:\nProject: {self.project.name}\nGoals: {self.project.goals or 'None recorded.'}\nDescription: {self.project.description or 'None recorded.'}")
        if self.repository_knowledge:
            sections.append("Current Repository Implementation:\n" + "\n".join(f"- [{item.kind}] {item.file_path}: {item.summary}" for item in self.repository_knowledge))
        if self.decisions:
            sections.append("Project Memory / Decisions:\n" + "\n".join(f"- {item.title}: {item.details} Reasoning: {item.reasoning}" for item in self.decisions))
        research_items = [item for item in self.knowledge if item.kind == "research"]
        other_knowledge = [item for item in self.knowledge if item.kind != "research"]
        if research_items:
            sections.append("Research / Future Plans:\n" + "\n".join(f"- {item.title}: {item.body}" for item in research_items))
        if other_knowledge:
            sections.append("Other Project Knowledge:\n" + "\n".join(f"- [{item.kind}] {item.title}: {item.body}" for item in other_knowledge))
        if self.tasks:
            sections.append("Tasks:\n" + "\n".join(f"- [{item.status.value}] {item.title}: {item.description}" for item in self.tasks))
        if len(sections) == 2:
            sections.append("No relevant stored memory found.")
        return "\n\n".join(sections)


class MemoryRetrievalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def retrieve(self, query: str, project_id: int | None = None, limit: int = 5) -> RetrievedMemory:
        terms = self._terms(query)
        project = self.db.get(Project, project_id) if project_id is not None else None
        decisions = self._ranked(self._project_rows(select(Decision), Decision.project_id, project_id), terms, query, {"title": 5, "details": 3, "reasoning": 2}, limit)
        knowledge = self._ranked(self._project_rows(select(KnowledgeItem), KnowledgeItem.project_id, project_id), terms, query, {"title": 5, "body": 3, "kind": 1}, limit)
        tasks = self._ranked(self._project_rows(select(Task), Task.project_id, project_id), terms, query, {"title": 5, "description": 3, "assigned_agent": 1, "status": 1, "priority": 1}, limit)
        repository_knowledge = RepositoryService(self.db).retrieve(query, project_id=project_id, limit=limit)
        return RetrievedMemory(project=project, decisions=decisions, knowledge=knowledge, tasks=tasks, repository_knowledge=repository_knowledge)

    def _project_rows(self, stmt, project_column, project_id: int | None):
        if project_id is not None:
            stmt = stmt.where(project_column == project_id)
        return self.db.scalars(stmt).all()

    def _ranked(self, rows: list, terms: set[str], query: str, field_weights: dict[str, int], limit: int) -> list:
        scored = []
        phrase = query.strip().lower()
        for row in rows:
            score = 0
            for field, weight in field_weights.items():
                value = str(getattr(row, field, "") or "").lower()
                if phrase and phrase in value:
                    score += weight * 4
                for term in terms:
                    if term == value:
                        score += weight * 3
                    elif value.startswith(term):
                        score += weight * 2
                    elif term in value:
                        score += weight
            if isinstance(row, KnowledgeItem) and row.kind == "research":
                score += 1
            if isinstance(row, Decision):
                score += 1
            if score > 0 or not terms:
                scored.append((score, row))
        scored.sort(key=lambda item: (item[0], getattr(item[1], "created_at", None)), reverse=True)
        return [row for _, row in scored[:limit]]

    def _terms(self, query: str) -> set[str]:
        stop_words = {"a", "an", "and", "are", "build", "for", "how", "is", "of", "or", "the", "this", "to", "we", "what", "with"}
        return {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2 and term not in stop_words}
