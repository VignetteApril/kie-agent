from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    app_name: str = "KIE Agent"
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    data_dir: Path = DEFAULT_DATA_DIR
    upload_dir: Path = DEFAULT_DATA_DIR / "uploads"
    output_dir: Path = DEFAULT_DATA_DIR / "outputs"
    log_dir: Path = DEFAULT_DATA_DIR / "logs"
    db_path: Path = DEFAULT_DATA_DIR / "tasks.db"

    llm_base_url: str = "http://192.168.137.2:8000/v1"
    llm_model: str = "Qwen3.5-35B-A3B-GPTQ-Int4"
    llm_api_key: str = "EMPTY"
    llm_timeout_seconds: int = 120
    llm_max_retries: int = 2
    llm_response_excerpt_limit: int = 500
    log_level: str = "INFO"
    worker_poll_seconds: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
