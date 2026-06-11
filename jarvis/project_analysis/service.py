from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime

from jarvis.database.models import Task
from jarvis.repositories.service import RepositoryService


class ProjectAnalysisService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repositories = RepositoryService(db)

    def analyze_project(self, project_id: int | None = None) -> list[str]:
        repositories = self.repositories.list_repositories(project_id)
        findings: list[str] = []
        if not repositories:
            return ["No repositories are registered for this project yet."]

        task_stmt = select(Task).where(Task.project_id == project_id) if project_id is not None else select(Task).where(Task.project_id.is_(None))
        open_tasks = self.db.scalars(task_stmt).all()
        for repository in repositories:
            self.repositories.refresh_freshness(repository)
            knowledge = self.repositories.knowledge_for_repository(repository.id)
            paths = {item.file_path.lower() for item in knowledge}
            if not repository.last_indexed_at:
                findings.append(f"{repository.name} has not been indexed yet.")
            else:
                age_days = max((datetime.utcnow() - repository.last_indexed_at).days, 0)
                findings.append(f"{repository.name} was indexed {age_days} days ago.")
            if repository.status == "Re-index Recommended":
                findings.append(f"{repository.name} has changed since the last index. Re-index recommended.")
            if repository.status == "Index Failed":
                findings.append(f"{repository.name} indexing failed: {repository.index_error or 'No error details stored.'}")
            if not any(path.endswith("readme.md") for path in paths):
                findings.append(f"{repository.name} is missing indexed README documentation.")
            service_docs = [path for path in paths if "service" in path]
            if service_docs and not any(path.endswith("readme.md") or "docs" in path for path in service_docs):
                findings.append(f"{repository.name} has service-layer code indexed but no obvious service documentation.")
            if not any("test" in path for path in paths):
                findings.append(f"{repository.name} has no obvious indexed test files.")
            if not any(item.kind == "database" for item in knowledge):
                findings.append(f"{repository.name} has no indexed database/schema summary.")
        self.db.commit()
        if open_tasks:
            findings.append(f"{len(open_tasks)} project tasks are available to prioritize against repository context.")
        return findings[:8]
