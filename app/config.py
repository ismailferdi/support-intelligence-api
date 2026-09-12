from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

ENV_FILE_PATH = Path(__file__).resolve().parents[1] / '.env'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding='utf-8'
    )

    openai_api_key: str
    base_url: str
    provider: str = "openai"
    openai_model: str = "gpt-oss-20b"
    database_url: str
    max_input_tokens: int = 3000
    review_confidence_threshold: float = 0.6


settings = Settings()
