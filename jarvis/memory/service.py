from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from jarvis.api.schemas import DecisionCreate, ProjectCreate
from jarvis.database.models import ConversationMessage, Decision, KnowledgeItem, Project


class MemoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_message(
        self,
        role: str,
        content: str,
        conversation_id: str | None = None,
        input_mode: str = "text",
        project_id: int | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            conversation_id=conversation_id or str(uuid4()),
            role=role,
            content=content,
            input_mode=input_mode,
            project_id=project_id,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def conversation_messages(self, conversation_id: str, limit: int = 20) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(desc(ConversationMessage.created_at))
            .limit(limit)
        )
        return list(reversed(self.db.scalars(stmt).all()))

    def full_conversation_messages(self, conversation_id: str, project_id: int | None = None) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at)
        )
        if project_id is None:
            stmt = stmt.where(ConversationMessage.project_id.is_(None))
        else:
            stmt = stmt.where(ConversationMessage.project_id == project_id)
        return self.db.scalars(stmt).all()

    def list_conversation_sessions(self, project_id: int | None = None) -> list[dict[str, object]]:
        stmt = select(ConversationMessage)
        if project_id is None:
            stmt = stmt.where(ConversationMessage.project_id.is_(None))
        else:
            stmt = stmt.where(ConversationMessage.project_id == project_id)
        messages = self.db.scalars(stmt.order_by(ConversationMessage.created_at)).all()

        sessions: dict[str, dict[str, object]] = {}
        for message in messages:
            session = sessions.setdefault(
                message.conversation_id,
                {
                    "conversation_id": message.conversation_id,
                    "project_id": message.project_id,
                    "label": self._conversation_fallback_label(message),
                    "last_activity_at": message.created_at,
                    "has_user_label": False,
                },
            )
            if message.role == "user" and not session["has_user_label"]:
                session["label"] = self._conversation_label(message.content, message)
                session["has_user_label"] = True
            session["last_activity_at"] = message.created_at

        ordered = sorted(sessions.values(), key=lambda item: item["last_activity_at"], reverse=True)
        for session in ordered:
            session.pop("has_user_label", None)
        return ordered

    def recent_messages(self, limit: int = 50) -> list[ConversationMessage]:
        stmt = select(ConversationMessage).order_by(desc(ConversationMessage.created_at)).limit(limit)
        return self.db.scalars(stmt).all()

    def create_project(self, payload: ProjectCreate) -> Project:
        project = Project(**payload.model_dump())
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def list_projects(self) -> list[Project]:
        return self.db.scalars(select(Project).order_by(Project.name)).all()

    def get_project(self, project_id: int | None) -> Project | None:
        if project_id is None:
            return None
        return self.db.get(Project, project_id)

    def create_decision(self, payload: DecisionCreate) -> Decision:
        decision = Decision(**payload.model_dump())
        self.db.add(decision)
        self.db.add(
            KnowledgeItem(
                title=f"Decision: {decision.title}",
                body=f"{decision.details}\n\nReasoning: {decision.reasoning}".strip(),
                kind="decision",
                source="decision",
                project_id=decision.project_id,
            )
        )
        self.db.commit()
        self.db.refresh(decision)
        return decision

    def list_decisions(self) -> list[Decision]:
        return self.db.scalars(select(Decision).order_by(desc(Decision.created_at))).all()

    def list_knowledge(self) -> list[KnowledgeItem]:
        return self.db.scalars(select(KnowledgeItem).order_by(desc(KnowledgeItem.created_at))).all()

    def _conversation_label(self, content: str, message: ConversationMessage) -> str:
        cleaned = " ".join(content.strip().split())
        if cleaned:
            return cleaned[:80]
        return self._conversation_fallback_label(message)

    def _conversation_fallback_label(self, message: ConversationMessage) -> str:
        return f"Conversation {message.created_at.strftime('%Y-%m-%d %I:%M %p').lstrip('0')}"
