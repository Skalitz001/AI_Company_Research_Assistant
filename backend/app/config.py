"""Environment-backed configuration for the research service."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secrets are only read by the backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    serper_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_default_model: str = "openrouter/auto"
    openrouter_model_suggestions: str = (
        "openrouter/auto,openrouter/free,~openai/gpt-latest"
    )
    openrouter_app_url: str | None = None
    crawler_user_agent: str = "CompanyResearchAssistant/1.0 (+research crawler)"
    discord_enabled: bool = False
    frontend_dist: Path = Path(__file__).resolve().parent / "static"
    port: int = 10000

    @property
    def model_suggestions(self) -> list[str]:
        values = [item.strip() for item in self.openrouter_model_suggestions.split(",")]
        return [item for item in values if item]

    @property
    def providers_ready(self) -> bool:
        return bool(self.serper_api_key and self.openrouter_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
