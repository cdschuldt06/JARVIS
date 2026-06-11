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
