"""Environment-based application settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Settings loaded from environment variables and the project .env file."""

    app_name: str = "AI Murder Mystery"
    app_env: str = "development"
    database_url: str = "sqlite:///./ai_murder_mystery.db"
    dify_api_url: str = ""
    dify_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
