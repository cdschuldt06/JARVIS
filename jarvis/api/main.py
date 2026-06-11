from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from jarvis.agents.unified_assistant import UnifiedAssistant
from jarvis.api.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationSessionRead,
    DecisionCreate,
    DecisionRead,
    HandoffCreate,
    HandoffRead,
    KnowledgeRead,
    MemoryRead,
    MessageRead,
    ProjectCreate,
    ProjectRead,
    ResearchRequest,
    ResearchResult,
    ResearchSaveRequest,
    ProjectAnalysisRead,
    RepositoryCreate,
    RepositoryIndexRead,
    RepositoryKnowledgeRead,
    RepositoryRead,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    UsageDashboardRead,
)
from jarvis.core.config import get_settings
from jarvis.database.session import get_db, init_db
from jarvis.handoffs.service import HandoffService
from jarvis.memory.service import MemoryService
from jarvis.project_analysis.service import ProjectAnalysisService
from jarvis.repositories.service import RepositoryService
from jarvis.research.service import ResearchService
from jarvis.tasks.service import TaskService
from jarvis.usage.service import UsageService

settings = get_settings()

app = FastAPI(title="Jarvis API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app_env": settings.app_env}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    result = UnifiedAssistant(db).chat(
        payload.message,
        conversation_id=payload.conversation_id,
        input_mode=payload.input_mode,
        project_id=payload.project_id,
    )
    return ChatResponse(conversation_id=result.conversation_id, response=result.response, activity=result.activity.__dict__)


@app.get("/chat/sessions", response_model=list[ConversationSessionRead])
def list_chat_sessions(project_id: int | None = None, db: Session = Depends(get_db)) -> list[ConversationSessionRead]:
    return MemoryService(db).list_conversation_sessions(project_id)


@app.get("/chat/conversations/{conversation_id}", response_model=list[MessageRead])
def get_chat_conversation(conversation_id: str, project_id: int | None = None, db: Session = Depends(get_db)) -> list[MessageRead]:
    return MemoryService(db).full_conversation_messages(conversation_id, project_id)


@app.get("/tasks", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskRead]:
    return TaskService(db).list_tasks()


@app.post("/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    return TaskService(db).create_task(payload)


@app.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskRead:
    return TaskService(db).update_task(task_id, payload)


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    TaskService(db).delete_task(task_id)


@app.get("/memory", response_model=MemoryRead)
def get_memory(db: Session = Depends(get_db)) -> MemoryRead:
    service = MemoryService(db)
    return MemoryRead(
        conversations=service.recent_messages(),
        projects=service.list_projects(),
        decisions=service.list_decisions(),
        knowledge=service.list_knowledge(),
    )


@app.get("/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    return MemoryService(db).list_projects()


@app.post("/projects", response_model=ProjectRead)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    return MemoryService(db).create_project(payload)


@app.post("/decisions", response_model=DecisionRead)
def create_decision(payload: DecisionCreate, db: Session = Depends(get_db)) -> DecisionRead:
    return MemoryService(db).create_decision(payload)


@app.post("/research", response_model=ResearchResult)
def run_research(payload: ResearchRequest, db: Session = Depends(get_db)) -> ResearchResult:
    if payload.project_id is None:
        raise HTTPException(status_code=422, detail="Research requires a Current Project. Select a project before running research.")
    return ResearchResult(**ResearchService(db).run_research(payload.query, payload.project_id))


@app.get("/research", response_model=list[KnowledgeRead])
def list_research(project_id: int | None = None, db: Session = Depends(get_db)) -> list[KnowledgeRead]:
    if project_id is None:
        raise HTTPException(status_code=422, detail="Saved research requires a Current Project. Select a project before viewing research.")
    return ResearchService(db).list_research(project_id)


@app.post("/research/save", response_model=KnowledgeRead)
def save_research(payload: ResearchSaveRequest, db: Session = Depends(get_db)) -> KnowledgeRead:
    if payload.project_id is None:
        raise HTTPException(status_code=422, detail="Saving research requires a Current Project. Select a project before saving research.")
    return ResearchService(db).save_research(payload.title, payload.summary, payload.sources, payload.project_id)


@app.get("/repositories", response_model=list[RepositoryRead])
def list_repositories(project_id: int | None = None, db: Session = Depends(get_db)) -> list[RepositoryRead]:
    return RepositoryService(db).list_repositories(project_id)


@app.post("/repositories", response_model=RepositoryRead)
def register_repository(payload: RepositoryCreate, db: Session = Depends(get_db)) -> RepositoryRead:
    return RepositoryService(db).register_repository(payload.name, payload.path, payload.description, payload.project_id)


@app.post("/repositories/{repository_id}/index", response_model=RepositoryIndexRead)
def index_repository(repository_id: int, db: Session = Depends(get_db)) -> RepositoryIndexRead:
    try:
        result = RepositoryService(db).index_repository(repository_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RepositoryIndexRead(repository=result.repository, indexed_files=result.indexed_files)


@app.get("/repositories/{repository_id}/knowledge", response_model=list[RepositoryKnowledgeRead])
def repository_knowledge(repository_id: int, db: Session = Depends(get_db)) -> list[RepositoryKnowledgeRead]:
    return RepositoryService(db).knowledge_for_repository(repository_id)


@app.get("/repositories/{repository_id}/summary")
def repository_summary(repository_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        summary = RepositoryService(db).repository_summary(repository_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"summary": summary}


@app.get("/project-analysis", response_model=ProjectAnalysisRead)
def project_analysis(project_id: int | None = None, db: Session = Depends(get_db)) -> ProjectAnalysisRead:
    return ProjectAnalysisRead(findings=ProjectAnalysisService(db).analyze_project(project_id))


@app.get("/usage", response_model=UsageDashboardRead)
def usage_dashboard(project_id: int | None = None, db: Session = Depends(get_db)) -> UsageDashboardRead:
    return UsageDashboardRead(**UsageService(db).dashboard(project_id))


@app.get("/handoffs", response_model=list[HandoffRead])
def list_handoffs(db: Session = Depends(get_db)) -> list[HandoffRead]:
    return HandoffService(db).list_handoffs()


@app.post("/handoffs", response_model=HandoffRead)
def create_handoff(payload: HandoffCreate, db: Session = Depends(get_db)) -> HandoffRead:
    if payload.project_id is None:
        raise HTTPException(status_code=422, detail="Codex handoff generation requires a Current Project. Select a project before generating a handoff.")
    return HandoffService(db).create_handoff(payload.user_request, payload.project_id)
