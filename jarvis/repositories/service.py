from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.database.models import Repository, RepositoryKnowledge


IMPORTANT_FILENAMES = {
    ".env.example",
    "README.md",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "next.config.ts",
    "next.config.js",
    "tailwind.config.ts",
    "tsconfig.json",
    "prisma/schema.prisma",
    "docker-compose.yml",
    "Dockerfile",
}
SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".prisma"}
SKIP_DIRS = {".git", ".next", ".venv", "__pycache__", "dist", "build", "node_modules", ".pytest_cache"}
COMPONENT_TERMS = (
    "agent",
    "api",
    "app",
    "client",
    "config",
    "database",
    "db",
    "import",
    "importer",
    "index",
    "job",
    "main",
    "model",
    "provider",
    "route",
    "schema",
    "server",
    "service",
    "task",
)


@dataclass(frozen=True)
class RepositoryIndexResult:
    repository: Repository
    indexed_files: int


@dataclass(frozen=True)
class RepositoryConfidence:
    files_used: int
    knowledge_items_used: int
    last_indexed_at: datetime | None
    confidence: str


class RepositoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register_repository(self, name: str, path: str, description: str = "", project_id: int | None = None) -> Repository:
        repository = Repository(name=name, path=path, description=description, project_id=project_id)
        self.db.add(repository)
        self.db.commit()
        self.db.refresh(repository)
        return repository

    def list_repositories(self, project_id: int | None = None) -> list[Repository]:
        stmt = select(Repository)
        if project_id is not None:
            stmt = stmt.where(Repository.project_id == project_id)
        repositories = self.db.scalars(stmt.order_by(Repository.updated_at.desc())).all()
        for repository in repositories:
            self.refresh_freshness(repository)
        if repositories:
            self.db.commit()
        return repositories

    def index_repository(self, repository_id: int) -> RepositoryIndexResult:
        repository = self.db.get(Repository, repository_id)
        if repository is None:
            raise ValueError("Repository not found.")

        try:
            root = Path(repository.path).expanduser()
            if not root.exists() or not root.is_dir():
                raise ValueError("Repository path must be an existing local folder.")

            self.db.query(RepositoryKnowledge).filter(RepositoryKnowledge.repository_id == repository.id).delete()
            entries = self._index_entries(root)
            for relative_path, kind, summary in entries:
                self.db.add(
                    RepositoryKnowledge(
                        repository_id=repository.id,
                        file_path=relative_path,
                        kind=kind,
                        summary=summary,
                    )
                )
            repository.last_indexed_at = datetime.utcnow()
            repository.last_known_modified_at = self._repository_modified_at(root)
            repository.files_indexed = len({relative_path for relative_path, kind, summary in entries if relative_path != "."})
            repository.index_status = "up_to_date"
            repository.index_error = ""
            self.db.commit()
            self.db.refresh(repository)
            return RepositoryIndexResult(repository=repository, indexed_files=len(entries))
        except Exception as exc:
            repository.index_status = "index_failed"
            repository.index_error = str(exc)
            self.db.commit()
            raise

    def knowledge_for_repository(self, repository_id: int) -> list[RepositoryKnowledge]:
        stmt = select(RepositoryKnowledge).where(RepositoryKnowledge.repository_id == repository_id)
        return self.db.scalars(stmt.order_by(RepositoryKnowledge.kind, RepositoryKnowledge.file_path)).all()

    def retrieve(self, query: str, project_id: int | None = None, limit: int = 8) -> list[RepositoryKnowledge]:
        terms = self._terms(query)
        stmt = select(RepositoryKnowledge).join(Repository)
        if project_id is not None:
            stmt = stmt.where(Repository.project_id == project_id)
        rows = self.db.scalars(stmt).all()

        scored: list[tuple[int, RepositoryKnowledge]] = []
        phrase = query.strip().lower()
        for row in rows:
            haystack = f"{row.file_path} {row.kind} {row.summary}".lower()
            score = 0
            if phrase and phrase in haystack:
                score += 10
            for term in terms:
                if term in row.file_path.lower():
                    score += 5
                if term in row.summary.lower():
                    score += 3
                if term in row.kind.lower():
                    score += 1
            if score > 0 or not terms:
                scored.append((score, row))

        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [row for _, row in scored[:limit]]

    def confidence_for_items(self, items: list[RepositoryKnowledge]) -> RepositoryConfidence:
        if not items:
            return RepositoryConfidence(files_used=0, knowledge_items_used=0, last_indexed_at=None, confidence="Low")
        files_used = len({item.file_path for item in items})
        last_indexed_at = max((item.repository.last_indexed_at for item in items if item.repository.last_indexed_at), default=None)
        status_penalty = any(item.repository.status != "Up To Date" for item in items)
        age_penalty = bool(last_indexed_at and datetime.utcnow() - last_indexed_at > timedelta(days=14))
        if files_used >= 5 and len(items) >= 8 and not status_penalty and not age_penalty:
            confidence = "High"
        elif files_used >= 2 and len(items) >= 3 and not age_penalty:
            confidence = "Medium"
        else:
            confidence = "Low"
        return RepositoryConfidence(
            files_used=files_used,
            knowledge_items_used=len(items),
            last_indexed_at=last_indexed_at,
            confidence=confidence,
        )

    def refresh_freshness(self, repository: Repository) -> None:
        if repository.files_indexed == 0 and repository.knowledge:
            repository.files_indexed = len({item.file_path for item in repository.knowledge if item.file_path != "."})
        root = Path(repository.path).expanduser()
        if not root.exists() or not root.is_dir():
            if repository.last_indexed_at is None:
                repository.index_status = "not_indexed"
            return
        repository.last_known_modified_at = self._repository_modified_at(root)
        if repository.index_status == "index_failed":
            return
        if repository.last_indexed_at is None:
            repository.index_status = "not_indexed"
        elif repository.last_known_modified_at and repository.last_known_modified_at > repository.last_indexed_at:
            repository.index_status = "reindex_recommended"
        else:
            repository.index_status = "up_to_date"

    def repository_summary(self, repository_id: int) -> str:
        repository = self.db.get(Repository, repository_id)
        if repository is None:
            raise ValueError("Repository not found.")
        knowledge = self.knowledge_for_repository(repository_id)
        if not knowledge:
            return "Repository has not been indexed yet."

        sections = [
            f"Repository: {repository.name}",
            "Summary source: indexed repository knowledge only.",
            f"Registered description: {repository.description or 'No description stored.'}",
        ]
        for kind in ("readme", "manifest", "database", "entrypoint", "component", "config"):
            items = [item for item in knowledge if item.kind == kind]
            if items:
                sections.append(f"{kind.title()} (current repository implementation):\n" + "\n".join(f"- {item.file_path}: {item.summary}" for item in items[:8]))
        return "\n\n".join(sections)

    def _index_entries(self, root: Path) -> list[tuple[str, str, str]]:
        selected = self._important_paths(root)
        entries: list[tuple[str, str, str]] = []
        for path in selected:
            relative = path.relative_to(root).as_posix()
            kind = self._kind(relative, path)
            entries.append((relative, kind, self._summarize_file(root, path, kind)))
        if selected:
            entries.insert(0, (".", "structure", self._summarize_structure(root, selected)))
        return entries[:80]

    def _important_paths(self, root: Path) -> list[Path]:
        paths: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file() or self._skipped(path, root):
                continue
            relative = path.relative_to(root).as_posix()
            if relative in IMPORTANT_FILENAMES or path.name in IMPORTANT_FILENAMES:
                paths.append(path)
                continue
            if path.suffix in SOURCE_EXTENSIONS and any(term in path.stem.lower() or term in relative.lower() for term in COMPONENT_TERMS):
                paths.append(path)
            if len(paths) >= 79:
                break
        return sorted(paths, key=lambda item: item.relative_to(root).as_posix())

    def _repository_modified_at(self, root: Path) -> datetime | None:
        latest: datetime | None = None
        checked = 0
        for path in root.rglob("*"):
            if self._skipped(path, root):
                continue
            try:
                modified = datetime.utcfromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if latest is None or modified > latest:
                latest = modified
            checked += 1
            if checked >= 1000:
                break
        return latest

    def _skipped(self, path: Path, root: Path) -> bool:
        relative_parts = path.relative_to(root).parts
        return any(part in SKIP_DIRS for part in relative_parts)

    def _summarize_file(self, root: Path, path: Path, kind: str) -> str:
        relative = path.relative_to(root).as_posix()
        text = self._read_text(path)
        if path.name == "package.json":
            return self._package_summary(text)
        if path.name == "requirements.txt":
            deps = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
            return f"Python dependency manifest with {len(deps)} dependencies: {', '.join(deps[:8])}."
        if relative == "prisma/schema.prisma":
            models = re.findall(r"model\s+(\w+)", text)
            return f"Prisma database schema defining models: {', '.join(models[:12]) or 'none detected'}."
        if kind == "readme":
            return self._readme_summary(text)
        return self._source_summary(relative, text)

    def _summarize_structure(self, root: Path, selected: list[Path]) -> str:
        folders = sorted({path.relative_to(root).parts[0] for path in selected if len(path.relative_to(root).parts) > 1})
        files = [path.relative_to(root).as_posix() for path in selected[:12]]
        return f"Indexed folders: {', '.join(folders[:12]) or 'root only'}. Important files: {', '.join(files)}."

    def _package_summary(self, text: str) -> str:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return "JavaScript package manifest."
        scripts = ", ".join(sorted((payload.get("scripts") or {}).keys())[:8])
        deps = list((payload.get("dependencies") or {}).keys()) + list((payload.get("devDependencies") or {}).keys())
        return f"JavaScript package manifest. Scripts: {scripts or 'none listed'}. Dependencies include: {', '.join(deps[:10]) or 'none listed'}."

    def _readme_summary(self, text: str) -> str:
        lines = [line.strip("# ").strip() for line in text.splitlines() if line.strip()]
        return "README summary: " + " ".join(lines[:5])[:700]

    def _source_summary(self, relative: str, text: str) -> str:
        names = re.findall(r"(?:class|def|function|const|export function|export class)\s+([A-Za-z0-9_]+)", text)
        imports = len(re.findall(r"^(?:import|from)\s+", text, re.MULTILINE))
        role = self._role_from_path(relative)
        details = f" Defines {', '.join(names[:8])}." if names else ""
        return f"{role} Imports/dependencies detected: {imports}.{details}".strip()

    def _role_from_path(self, relative: str) -> str:
        lowered = relative.lower()
        if "provider" in lowered or "import" in lowered:
            return "Provider/import component."
        if "service" in lowered:
            return "Service layer component."
        if "api" in lowered or "route" in lowered:
            return "API/routing component."
        if "schema" in lowered or "model" in lowered:
            return "Data model/schema component."
        if "config" in lowered:
            return "Configuration component."
        if "app" in lowered or "main" in lowered or "index" in lowered:
            return "Application entry/component."
        return "Source component."

    def _kind(self, relative: str, path: Path) -> str:
        lowered = relative.lower()
        if path.name.lower() == "readme.md":
            return "readme"
        if path.name in {"package.json", "requirements.txt", "pyproject.toml"}:
            return "manifest"
        if "schema" in lowered or path.suffix == ".prisma":
            return "database"
        if any(term in lowered for term in ("main", "app", "index", "server")):
            return "entrypoint"
        if "config" in lowered or path.name.startswith(".env"):
            return "config"
        return "component"

    def _read_text(self, path: Path, max_chars: int = 12000) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        except OSError:
            return ""

    def _terms(self, query: str) -> set[str]:
        stop_words = {"a", "an", "and", "are", "for", "how", "is", "of", "or", "the", "this", "to", "we", "what", "with"}
        return {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2 and term not in stop_words}
