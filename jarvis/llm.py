from openai import OpenAI
from sqlalchemy.orm import Session

from jarvis.core.config import get_settings
from jarvis.usage.service import UsageService


class OpenAIClient:
    def __init__(self, db: Session | None = None) -> None:
        settings = get_settings()
        self.model = settings.openai_model
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.db = db

    def chat(
        self,
        messages: list[dict[str, str]],
        operation_type: str = "chat",
        project_id: int | None = None,
        conversation_id: str | None = None,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": message["role"],
                    "content": message["content"],
                }
                for message in messages
            ],
        )
        if self.db is not None:
            UsageService(self.db).log_openai_usage(
                model=self.model,
                operation_type=operation_type,
                usage=response.usage,
                project_id=project_id,
                conversation_id=conversation_id,
            )
        return response.choices[0].message.content or ""
