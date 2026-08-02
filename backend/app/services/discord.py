"""Discord PDF delivery using caller-supplied, non-persisted credentials."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Final

import httpx

from ..schemas import DiscordApplicant, ResearchReport
from .pdf import render_pdf, safe_filename

DISCORD_MESSAGES_URL: Final[str] = "https://discord.com/api/v10/channels/{channel_id}/messages"


class DiscordDeliveryError(RuntimeError):
    """A safe, user-facing Discord delivery failure."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _retry_at(response: httpx.Response) -> str | None:
    """Convert Discord's retry headers into a readable UTC time."""
    retry_after = response.headers.get("retry-after")
    if not retry_after:
        return None
    try:
        retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, float(retry_after)))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(retry_after).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None
    return retry_at.strftime("%Y-%m-%d %H:%M UTC")


def _message_content(report: ResearchReport, applicant: DiscordApplicant) -> str:
    """Build a bounded plain-text Discord message; report details stay in the PDF."""
    return (
        "Company research report\n"
        f"Applicant: {applicant.name}\n"
        f"Email: {applicant.email}\n"
        f"Company: {report.company.name}\n"
        f"Website: {report.company.website}"
    )[:1900]


async def deliver_report_to_discord(
    client: httpx.AsyncClient,
    *,
    report: ResearchReport,
    applicant: DiscordApplicant,
    bot_token: str,
    channel_id: str,
) -> None:
    """Generate the validated report PDF and attach it to a Discord message."""
    try:
        pdf_data = render_pdf(report)
    except Exception as exc:
        raise DiscordDeliveryError("DISCORD_PDF_FAILED", "The report PDF could not be generated for Discord.", retryable=True) from exc

    payload = {
        "content": _message_content(report, applicant),
        "allowed_mentions": {"parse": []},
    }
    files = {
        "files[0]": (
            safe_filename(report.company.name),
            pdf_data,
            "application/pdf",
        )
    }
    headers = {"Authorization": f"Bot {bot_token}"}
    try:
        response = await client.post(
            DISCORD_MESSAGES_URL.format(channel_id=channel_id),
            headers=headers,
            data={"payload_json": json.dumps(payload, ensure_ascii=False)},
            files=files,
            timeout=30.0,
        )
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise DiscordDeliveryError(
            "DISCORD_UNAVAILABLE",
            "Discord did not respond. Retry sending the report.",
            retryable=True,
        ) from exc

    if 200 <= response.status_code < 300:
        return
    if response.status_code in {401, 403}:
        raise DiscordDeliveryError(
            "DISCORD_UNAUTHORIZED",
            "Discord rejected the bot token or channel permission. Check the token and channel ID.",
        )
    if response.status_code == 404:
        raise DiscordDeliveryError(
            "DISCORD_CHANNEL_NOT_FOUND",
            "Discord could not find that channel. Check the channel ID and bot access.",
        )
    if response.status_code == 429:
        retry_at = _retry_at(response)
        message = "Discord rate limit reached. Retry sending the report."
        if retry_at:
            message = f"Discord rate limit reached. Retry after {retry_at}."
        raise DiscordDeliveryError("DISCORD_RATE_LIMITED", message, retryable=True)
    if response.status_code >= 500:
        raise DiscordDeliveryError(
            "DISCORD_UNAVAILABLE",
            "Discord is temporarily unavailable. Retry sending the report.",
            retryable=True,
        )
    raise DiscordDeliveryError(
        "DISCORD_DELIVERY_FAILED",
        "Discord rejected the report delivery request.",
    )
