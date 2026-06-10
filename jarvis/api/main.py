from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from jarvis.agents.jarvis_agent import JarvisAgent
from jarvis.api.schemas import (
    ChatRequest,
    ChatResponse,
    DecisionCreate,
    DecisionRead,
    HandoffCreate,
    HandoffRead,
    MemoryRead,
    ProjectCreate,
    ProjectRead,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from jarvis.core.config import get_settings
from jarvis.database.session import get_db, init_db
from jarvis.handoffs.service import HandoffService
from jarvis.memory.service import MemoryService
from jarvis.tasks.service import TaskService

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
    conversation_id, response = JarvisAgent(db).chat(
        payload.message,
        conversation_id=payload.conversation_id,
        input_mode=payload.input_mode,
    )
    return ChatResponse(conversation_id=conversation_id, response=response)


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


@app.get("/handoffs", response_model=list[HandoffRead])
def list_handoffs(db: Session = Depends(get_db)) -> list[HandoffRead]:
    return HandoffService(db).list_handoffs()


@app.post("/handoffs", response_model=HandoffRead)
def create_handoff(payload: HandoffCreate, db: Session = Depends(get_db)) -> HandoffRead:
    return HandoffService(db).create_handoff(payload.user_request, payload.project_id)
