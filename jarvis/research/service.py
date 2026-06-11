import json
from typing import Any

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.core.config import get_settings
from jarvis.database.models import KnowledgeItem
from jarvis.memory.retrieval import MemoryRetrievalService
from jarvis.usage.service import UsageService


class ResearchService:
    def __init__(self, db: Session) -> None:
        settings = get_settings()
        self.db = db
        self.model = settings.openai_research_model
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.retrieval = MemoryRetrievalService(db)

    def run_research(self, query: str, project_id: int | None = None, include_project_context: bool = True) -> dict[str, object]:
        memory_context = self.retrieval.retrieve(query, project_id=project_id).to_prompt_context() if include_project_context else ""
        context_instruction = (
            f"Use the project context when relevant.\n\nProject context:\n{memory_context}\n\n"
            if include_project_context
            else "This is a general research request. Do not add a project relevance section unless the user explicitly asks how it relates to Jarvis or the current project.\n\n"
        )
        response = self.client.responses.create(
            model=self.model,
            tools=[{"type": "web_search"}],
            input=f"Research this question for Jarvis. Ground fresh claims in web sources.\n\n{context_instruction}Research query: {query}\n\nReturn a concise summary, key findings, and cite sources.",
        )
        payload = response.model_dump()
        UsageService(self.db).log_openai_usage(
            model=self.model,
            operation_type="research",
            usage=payload.get("usage"),
            project_id=project_id,
        )
        sources = self._extract_sources(payload)
        return {
            "query": query,
            "model": self.model,
            "summary": response.output_text,
            "sources": sources,
        }

    def save_research(self, title: str, summary: str, sources: list[str], project_id: int | None = None) -> KnowledgeItem:
        item = KnowledgeItem(
            title=title,
            body=summary,
            kind="research",
            source=json.dumps({"urls": sources}),
            project_id=project_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_research(self, project_id: int | None = None) -> list[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(KnowledgeItem.kind == "research")
        if project_id is not None:
            stmt = stmt.where(KnowledgeItem.project_id == project_id)
        return self.db.scalars(stmt.order_by(KnowledgeItem.created_at.desc())).all()

    def _extract_sources(self, payload: Any) -> list[str]:
        urls: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                url = value.get("url")
                if isinstance(url, str) and url.startswith(("http://", "https://")) and url not in urls:
                    urls.append(url)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)
        return urls
