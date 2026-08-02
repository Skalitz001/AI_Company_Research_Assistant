"""Browser-safe configuration and process health endpoints."""
from fastapi import APIRouter

from ..config import get_settings
from ..schemas import ConfigResponse, HealthResponse

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/config", response_model=ConfigResponse)
async def config() -> ConfigResponse:
    settings = get_settings()
    return ConfigResponse(
        ready=settings.providers_ready,
        default_model=settings.effective_default_model,
        model_suggestions=settings.model_suggestions,
        discord_enabled=settings.discord_enabled,
    )
