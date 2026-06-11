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
    activity: "ToolActivityRead | None" = None


class ToolActivityRead(BaseModel):
    actions: list[str] = []
    model: str = ""
    memory_retrieved: bool = False
    research_performed: bool = False
    handoff_generated: bool = False
    research_saved: bool = False
    repository_retrieved: bool = False
    news_provider_used: str | None = None
    market_provider_used: str | None = None
    research_fallback_used: bool = False
    market_context: dict[str, object] | None = None
    memory_counts: dict[str, int] | None = None
    repository_context: dict[str, object] | None = None
    sources: list[str] | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: str
    role: str
    content: str
    input_mode: str
    project_id: int | None
    created_at: datetime


class ConversationSessionRead(BaseModel):
    conversation_id: str
    project_id: int | None
    label: str
    last_activity_at: datetime


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


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1)
    project_id: int | None = None


class ResearchResult(BaseModel):
    query: str
    model: str
    summary: str
    sources: list[str] = []


class ResearchSaveRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1)
    sources: list[str] = []
    project_id: int | None = None


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    path: str = Field(min_length=1)
    description: str = ""
    project_id: int | None = None


class RepositoryRead(RepositoryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_indexed_at: datetime | None
    last_known_modified_at: datetime | None
    files_indexed: int
    index_status: str
    index_error: str
    knowledge_items_count: int
    status: str
    created_at: datetime
    updated_at: datetime


class RepositoryKnowledgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    file_path: str
    summary: str
    kind: str
    created_at: datetime


class RepositoryIndexRead(BaseModel):
    repository: RepositoryRead
    indexed_files: int


class ProjectAnalysisRead(BaseModel):
    findings: list[str]


class UsageLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    model: str
    operation_type: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    project_id: int | None
    conversation_id: str | None


class UsageGroupRead(BaseModel):
    name: str
    cost: float
    tokens: int
    calls: int


class UsageDashboardRead(BaseModel):
    estimated: bool
    totals: dict[str, float]
    by_model: list[UsageGroupRead]
    by_operation: list[UsageGroupRead]
    recent: list[UsageLogRead]


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
