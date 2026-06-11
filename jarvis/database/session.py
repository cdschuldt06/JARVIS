from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from jarvis.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

if settings.database_url.startswith("sqlite:///./"):
    db_path = Path(settings.database_url.replace("sqlite:///./", "", 1))
    db_path.parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from jarvis.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_schema_updates()


def _apply_sqlite_schema_updates() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "conversation_messages" in table_names:
        columns = {column["name"] for column in inspector.get_columns("conversation_messages")}
        if "project_id" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE conversation_messages ADD COLUMN project_id INTEGER REFERENCES projects(id)"))

    if "repositories" in table_names:
        columns = {column["name"] for column in inspector.get_columns("repositories")}
        with engine.begin() as connection:
            if "last_known_modified_at" not in columns:
                connection.execute(text("ALTER TABLE repositories ADD COLUMN last_known_modified_at DATETIME"))
            if "files_indexed" not in columns:
                connection.execute(text("ALTER TABLE repositories ADD COLUMN files_indexed INTEGER DEFAULT 0"))
            if "index_status" not in columns:
                connection.execute(text("ALTER TABLE repositories ADD COLUMN index_status VARCHAR(40) DEFAULT 'not_indexed'"))
            if "index_error" not in columns:
                connection.execute(text("ALTER TABLE repositories ADD COLUMN index_error TEXT DEFAULT ''"))
