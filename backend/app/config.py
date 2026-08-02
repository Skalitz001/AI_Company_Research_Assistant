"""Environment-backed configuration for the research service."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

FREE_MODEL_ROUTER = "openrouter/free"
DEFAULT_FREE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


def is_free_model_id(model_id: str) -> bool:
    return model_id == FREE_MODEL_ROUTER or model_id.endswith(":free")



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
    openrouter_default_model: str = DEFAULT_FREE_MODEL
    openrouter_model_suggestions: str = (
        "nvidia/nemotron-3-super-120b-a12b:free,openai/gpt-oss-20b:free,"
        "google/gemma-4-26b-a4b-it:free,openrouter/free"
    )
    openrouter_app_url: str | None = None
    crawler_user_agent: str = "CompanyResearchAssistant/1.0 (+research crawler)"
    discord_enabled: bool = False
    frontend_dist: Path = Path(__file__).resolve().parent / "static"
    port: int = 10000

    @property
    def effective_default_model(self) -> str:
        return self.openrouter_default_model if is_free_model_id(self.openrouter_default_model) else DEFAULT_FREE_MODEL

    @property
    def model_suggestions(self) -> list[str]:
        values = [item.strip() for item in self.openrouter_model_suggestions.split(",")]
        suggestions = [item for item in values if item and is_free_model_id(item)]
        return suggestions or [DEFAULT_FREE_MODEL]

    @property
    def providers_ready(self) -> bool:
        return bool(self.serper_api_key and self.openrouter_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
