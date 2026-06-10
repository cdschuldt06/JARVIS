from sqlalchemy.orm import Session

from jarvis.agents.base import Agent
from jarvis.llm import OpenAIClient
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
        self.llm = llm or OpenAIClient()

    def chat(self, user_message: str, conversation_id: str | None = None, input_mode: str = "text") -> tuple[str, str]:
        user_record = self.memory.add_message("user", user_message, conversation_id=conversation_id, input_mode=input_mode)
        history = self.memory.conversation_messages(user_record.conversation_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend({"role": item.role, "content": item.content} for item in history)
        response_text = self.llm.chat(messages)
        self.memory.add_message("assistant", response_text, conversation_id=user_record.conversation_id)
        return user_record.conversation_id, response_text

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "responsibilities": self.responsibilities}
