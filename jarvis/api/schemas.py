from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from jarvis.database.models import HandoffStatus, ProjectStatus, TaskPriority, TaskStatus


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    project_id: int | None = None
    input_mode: Literal["text", "voice"] = "text"


class ChatResponse(BaseModel):
    conversation_id: str
    response: str


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: str
    role: str
    content: str
    input_mode: str
    project_id: int | None
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    status: ProjectStatus = ProjectStatus.active
    goals: str = ""


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    details: str = Field(min_length=1)
    reasoning: str = ""
    project_id: int | None = None


class DecisionRead(DecisionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class KnowledgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    kind: str
    source: str
    project_id: int | None
    created_at: datetime


class MemoryRead(BaseModel):
    conversations: list[MessageRead]
    projects: list[ProjectRead]
    decisions: list[DecisionRead]
    knowledge: list[KnowledgeRead]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    assigned_agent: str = "JarvisAgent"
    status: TaskStatus = TaskStatus.pending
    priority: TaskPriority = TaskPriority.medium
    project_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    assigned_agent: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    project_id: int | None = None


class TaskRead(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class HandoffCreate(BaseModel):
    user_request: str = Field(min_length=1)
    project_id: int | None = None


class HandoffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    user_request: str
    brief: str
    status: HandoffStatus
    created_at: datetime
