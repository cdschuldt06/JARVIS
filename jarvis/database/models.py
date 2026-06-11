from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jarvis.database.session import Base


class ProjectStatus(str, Enum):
    active = "active"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class TaskPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class HandoffStatus(str, Enum):
    draft = "draft"
    delivered = "delivered"
    accepted = "accepted"
    superseded = "superseded"


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(80), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    input_mode: Mapped[str] = mapped_column(String(20), default="text")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project | None"] = relationship(back_populates="conversation_messages")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ProjectStatus] = mapped_column(default=ProjectStatus.active)
    goals: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    decisions: Mapped[list["Decision"]] = relationship(back_populates="project")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")
    handoffs: Mapped[list["CodexHandoff"]] = relationship(back_populates="project")
    conversation_messages: Mapped[list[ConversationMessage]] = relationship(back_populates="project")
    repositories: Mapped[list["Repository"]] = relationship(back_populates="project")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    details: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project | None] = relationship(back_populates="decisions")


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(80), default="note")
    source: Mapped[str] = mapped_column(Text, default="manual")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    assigned_agent: Mapped[str] = mapped_column(String(80), default="JarvisAgent")
    status: Mapped[TaskStatus] = mapped_column(default=TaskStatus.pending)
    priority: Mapped[TaskPriority] = mapped_column(default=TaskPriority.medium)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped[Project | None] = relationship(back_populates="tasks")


class CodexHandoff(Base):
    __tablename__ = "codex_handoffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    user_request: Mapped[str] = mapped_column(Text)
    brief: Mapped[str] = mapped_column(Text)
    status: Mapped[HandoffStatus] = mapped_column(default=HandoffStatus.draft)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project | None] = relationship(back_populates="handoffs")


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    path: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_known_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    files_indexed: Mapped[int] = mapped_column(Integer, default=0)
    index_status: Mapped[str] = mapped_column(String(40), default="not_indexed")
    index_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped[Project | None] = relationship(back_populates="repositories")
    knowledge: Mapped[list["RepositoryKnowledge"]] = relationship(back_populates="repository", cascade="all, delete-orphan")

    @property
    def knowledge_items_count(self) -> int:
        return len(self.knowledge)

    @property
    def status(self) -> str:
        if self.index_status == "index_failed":
            return "Index Failed"
        if self.last_indexed_at is None:
            return "Not Indexed"
        if self.last_known_modified_at and self.last_known_modified_at > self.last_indexed_at:
            return "Re-index Recommended"
        return "Up To Date"


class RepositoryKnowledge(Base):
    __tablename__ = "repository_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"))
    file_path: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(80), default="file")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    repository: Mapped[Repository] = relationship(back_populates="knowledge")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    model: Mapped[str] = mapped_column(String(120), index=True)
    operation_type: Mapped[str] = mapped_column(String(40), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
