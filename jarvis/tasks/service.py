from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.api.schemas import TaskCreate, TaskUpdate
from jarvis.database.models import Task


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_tasks(self) -> list[Task]:
        return self.db.scalars(select(Task).order_by(Task.created_at.desc())).all()

    def create_task(self, payload: TaskCreate) -> Task:
        task = Task(**payload.model_dump())
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def update_task(self, task_id: int, payload: TaskUpdate) -> Task:
        task = self.db.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, key, value)
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete_task(self, task_id: int) -> None:
        task = self.db.get(Task, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        self.db.delete(task)
        self.db.commit()
