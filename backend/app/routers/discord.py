"""Browser-facing Discord delivery endpoint."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..config import get_settings
from ..schemas import DiscordRequest, DiscordResponse, ResearchError
from ..services.discord import DiscordDeliveryError, deliver_report_to_discord

router = APIRouter(prefix="/api/v1", tags=["discord"])
MAX_BODY = 1_500_000


def _error_response(error: ResearchError, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error.model_dump(mode="json")})


@router.post("/discord", response_model=DiscordResponse)
async def discord(request: Request):
    settings = get_settings()
    if not settings.discord_enabled:
        return _error_response(
            ResearchError(
                code="DISCORD_DISABLED",
                message="Discord delivery is not enabled on this service.",
                retryable=False,
            ),
            503,
        )

    body = await request.body()
    if len(body) > MAX_BODY:
        return _error_response(
            ResearchError(code="DISCORD_INPUT_TOO_LARGE", message="The Discord request payload is too large.", retryable=False),
            413,
        )
    try:
        value = json.loads(body)
        payload = DiscordRequest.model_validate(value)
    except (json.JSONDecodeError, ValidationError, TypeError, AttributeError):
        return _error_response(
            ResearchError(
                code="INVALID_DISCORD_SETTINGS",
                message="Provide a report, applicant name and email, bot token, and numeric channel ID.",
                retryable=False,
            ),
            422,
        )

    client = getattr(request.app.state, "http_client", None)
    if client is None:
        return _error_response(
            ResearchError(code="DISCORD_UNAVAILABLE", message="Discord delivery is unavailable. Retry sending the report.", retryable=True),
            503,
        )
    try:
        await deliver_report_to_discord(
            client,
            report=payload.report,
            applicant=payload.applicant,
            bot_token=payload.bot_token,
            channel_id=payload.channel_id,
        )
    except DiscordDeliveryError as exc:
        status_code = {
            "DISCORD_UNAUTHORIZED": 401,
            "DISCORD_CHANNEL_NOT_FOUND": 404,
            "DISCORD_RATE_LIMITED": 429,
        }.get(exc.code, 503 if exc.retryable else 422)
        return _error_response(
            ResearchError(code=exc.code, message=exc.message, retryable=exc.retryable),
            status_code,
        )

    return JSONResponse(content=DiscordResponse().model_dump(mode="json"))
