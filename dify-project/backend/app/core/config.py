"""Environment-based application settings."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Settings loaded from environment variables and the project .env file."""

    app_name: str = "AI Murder Mystery"
    app_env: str = "development"
    database_url: str = "sqlite:///./ai_murder_mystery.db"
    dify_api_url: str = ""
    dify_character_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DIFY_CHARACTER_API_KEY", "DIFY_API_KEY"),
    )
    dify_director_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def dify_character_configured(self) -> bool:
        """Whether the character chat endpoint has the required Dify settings."""
        return bool(self.dify_api_url.strip() and self.dify_character_api_key.strip())

    @property
    def dify_director_configured(self) -> bool:
        """Whether the Director workflow has its independent Dify API key."""
        return bool(self.dify_api_url.strip() and self.dify_director_api_key.strip())


settings = Settings()
