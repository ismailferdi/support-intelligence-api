from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE_PATH = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from env file."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
    )

    openai_api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    openai_model: str = "openai/gpt-oss-20b"
    database_url: str = "postgres://admin:123456@127.0.0.1:5432/dummy"
    max_input_tokens: int = 3000
    max_output_tokens: int = 500
    request_timeout_seconds: int = 30
    postgres_user: str
    postgres_password: str
    postgres_db: str


settings = Settings()
