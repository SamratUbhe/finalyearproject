"""Application configuration module."""

from functools import lru_cache
import os
from pathlib import Path
from typing import Any, Union
from dotenv import dotenv_values, load_dotenv
from pydantic import BaseModel, ConfigDict, field_validator

# Always load absolute .env path if available
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"
if ENV_FILE_PATH.exists():
    load_dotenv(ENV_FILE_PATH, override=True)

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    class SettingsConfigDict(dict):
        """Fallback configuration dictionary for Settings."""
        pass

    class BaseSettings(BaseModel):
        """Fallback BaseSettings when pydantic-settings is not installed."""
        model_config = ConfigDict(extra="ignore")

        def __init__(self, **values: Any):
            config = getattr(self.__class__, "model_config", {})
            env_file = config.get("env_file", str(ENV_FILE_PATH)) if isinstance(config, dict) else str(ENV_FILE_PATH)
            file_vars = {}
            if os.path.exists(env_file):
                file_vars = {k.lower(): v for k, v in dotenv_values(env_file).items() if v is not None}

            env_vars = {k.lower(): v for k, v in os.environ.items()}
            merged = {**file_vars, **env_vars}

            init_data = {}
            for field_name, field_info in self.__class__.model_fields.items():
                if field_name in values:
                    init_data[field_name] = values[field_name]
                elif field_name.lower() in merged:
                    init_data[field_name] = merged[field_name.lower()]
                elif field_name.upper() in os.environ:
                    init_data[field_name] = os.environ[field_name.upper()]
                elif field_info.default is not ...:
                    init_data[field_name] = field_info.default

            init_data.update(values)
            super().__init__(**init_data)


class Settings(BaseSettings):
    """Runtime configuration loaded from environment and defaults."""

    app_name: str = "LOKI - Automated Code Vulnerability Reviewer"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    gemini_api_key: str = ""
    github_token: str = ""
    max_file_size_bytes: int = 1048576
    supported_extensions: list[str] = [".py", ".js", ".jsx", ".ts", ".tsx"]
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_model: str = "gemini-3.5-flash"
    gemini_temperature: float = 0.2
    gemini_max_retries: int = 4
    gemini_request_interval: float = 4.0
    agent_timeout_seconds: float = 60.0
    agent_max_concurrency: int = 2

    @field_validator("supported_extensions", mode="before")
    @classmethod
    def parse_supported_extensions(cls, v: Union[str, list[str]]) -> list[str]:
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",") if ext.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Dependency injection helper returning cached Settings singleton."""
    return Settings()


def reload_settings() -> Settings:
    """Clear settings cache and re-read environment/.env."""
    get_settings.cache_clear()
    return get_settings()


