
import httpx
import pytest

from backend.app.schemas import DiscordApplicant, ResearchReport
from backend.app.services.discord import DiscordDeliveryError, deliver_report_to_discord


def make_report() -> ResearchReport:
    return ResearchReport.model_validate(
        {
            "company": {
                "name": "Acme Labs",
                "website": "https://acme.example",
                "phone": None,
                "address": None,
                "country": "US",
                "industry": "Software",
            },
            "summary": "A concise report.",
            "products_services": ["Workflow software"],
            "pain_points": ["A hypothesis"],
            "competitors": [],
            "sources": [{"title": "Acme", "url": "https://acme.example", "source_type": "website"}],
            "warnings": [],
            "model_id": "openrouter/free",
        }
    )


@pytest.mark.asyncio
async def test_discord_delivery_posts_pdf_multipart_with_mentions_disabled():
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("authorization")
        observed["body"] = request.content
        return httpx.Response(200, json={"id": "message-id"})

    applicant = DiscordApplicant(name="Applicant", email="applicant@example.com")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await deliver_report_to_discord(
            client,
            report=make_report(),
            applicant=applicant,
            bot_token="secret-bot-token",
            channel_id="123456789012345678",
        )

    body = observed["body"]
    assert observed["url"] == "https://discord.com/api/v10/channels/123456789012345678/messages"
    assert observed["authorization"] == "Bot secret-bot-token"
    assert isinstance(body, bytes)
    assert b'name="payload_json"' in body
    assert b'"allowed_mentions": {"parse": []}' in body
    assert b'name="files[0]"' in body
    assert b'acme-labs-research-report.pdf' in body
    assert b"%PDF-" in body


@pytest.mark.asyncio
async def test_discord_rate_limit_is_retryable_without_echoing_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "0"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DiscordDeliveryError) as caught:
            await deliver_report_to_discord(
                client,
                report=make_report(),
                applicant=DiscordApplicant(name="Applicant", email="applicant@example.com"),
                bot_token="secret-bot-token",
                channel_id="123456789012345678",
            )

    assert caught.value.code == "DISCORD_RATE_LIMITED"
    assert caught.value.retryable is True
    assert "secret-bot-token" not in caught.value.message
