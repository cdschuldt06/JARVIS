from sqlalchemy.orm import Session

from jarvis.agents.base import Agent
from jarvis.llm import OpenAIClient
from jarvis.memory.retrieval import MemoryRetrievalService
from jarvis.memory.service import MemoryService


SYSTEM_PROMPT = """You are Jarvis, a persistent personal AI operating system.
You are the planner, memory manager, and implementation-brief author.
You do not claim to execute code, control computers, place trades, send email, or write to GitHub.
When implementation is needed, prepare context for Codex."""


class JarvisAgent(Agent):
    name = "JarvisAgent"
    responsibilities = ("chat", "planning", "memory_management", "knowledge_extraction", "task_creation")

    def __init__(self, db: Session, llm: OpenAIClient | None = None) -> None:
        self.memory = MemoryService(db)
        self.retrieval = MemoryRetrievalService(db)
        self.llm = llm or OpenAIClient(db)

    def chat(
        self,
        user_message: str,
        conversation_id: str | None = None,
        input_mode: str = "text",
        project_id: int | None = None,
    ) -> tuple[str, str]:
        user_record = self.memory.add_message(
            "user",
            user_message,
            conversation_id=conversation_id,
            input_mode=input_mode,
            project_id=project_id,
        )
        retrieved = self.retrieval.retrieve(user_message, project_id=project_id)
        history = self.memory.conversation_messages(user_record.conversation_id)
        messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nUse this retrieved memory when it is relevant. Do not invent memory that is not present.\n\n{retrieved.to_prompt_context()}"}]
        messages.extend({"role": item.role, "content": item.content} for item in history)
        response_text = self.llm.chat(messages, operation_type="chat", project_id=project_id, conversation_id=user_record.conversation_id)
        self.memory.add_message("assistant", response_text, conversation_id=user_record.conversation_id, project_id=project_id)
        return user_record.conversation_id, response_text

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "responsibilities": self.responsibilities}
