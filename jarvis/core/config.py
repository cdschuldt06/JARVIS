from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(default="sqlite:///./data/jarvis.db", alias="DATABASE_URL")
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_research_model: str = Field(default="gpt-5.5", alias="OPENAI_RESEARCH_MODEL")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")
    codex_cli_path: str = Field(default="codex", alias="CODEX_CLI_PATH")
    codex_working_directory: str = Field(default=r"C:\Projects\jarvis", alias="CODEX_WORKING_DIRECTORY")
    codex_default_sandbox: str = Field(default="read-only", alias="CODEX_DEFAULT_SANDBOX")
    codex_exec_timeout_seconds: int = Field(default=300, alias="CODEX_EXEC_TIMEOUT_SECONDS")
    codex_require_chatgpt_auth: bool = Field(default=True, alias="CODEX_REQUIRE_CHATGPT_AUTH")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_api_key(cls, value: str) -> str:
        if not value or value.strip() == "":
            raise ValueError("OPENAI_API_KEY is required. Add it to your .env file.")
        return value

    @field_validator("openai_model", "openai_research_model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        if not value or value.strip() == "":
            raise ValueError("OpenAI model names must not be empty.")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
