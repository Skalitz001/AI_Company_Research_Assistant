from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import app
from backend.app.routers import discord as discord_router


REPORT = {
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


def request_body(channel_id: str = "123456789012345678") -> dict:
    return {
        "report": REPORT,
        "applicant": {"name": "Applicant", "email": "applicant@example.com"},
        "bot_token": "secret-bot-token",
        "channel_id": channel_id,
    }


def test_discord_route_validates_numeric_channel_id(monkeypatch):
    settings = Settings(_env_file=None, discord_enabled=True)
    monkeypatch.setattr(discord_router, "get_settings", lambda: settings)

    with TestClient(app) as client:
        response = client.post("/api/v1/discord", json=request_body("not-numeric"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DISCORD_SETTINGS"


def test_discord_route_delivers_without_returning_token(monkeypatch):
    settings = Settings(_env_file=None, discord_enabled=True)
    calls: dict[str, object] = {}

    async def fake_delivery(client, **kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(discord_router, "get_settings", lambda: settings)
    monkeypatch.setattr(discord_router, "deliver_report_to_discord", fake_delivery)

    with TestClient(app) as client:
        response = client.post("/api/v1/discord", json=request_body())

    assert response.status_code == 200
    assert response.json() == {"status": "sent", "message": "Report sent to Discord."}
    assert calls["channel_id"] == "123456789012345678"
    assert calls["bot_token"] == "secret-bot-token"
    assert "secret-bot-token" not in response.text


def test_discord_route_is_disabled_without_feature_flag(monkeypatch):
    settings = Settings(_env_file=None, discord_enabled=False)
    monkeypatch.setattr(discord_router, "get_settings", lambda: settings)

    with TestClient(app) as client:
        response = client.post("/api/v1/discord", json=request_body())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DISCORD_DISABLED"
    assert "secret-bot-token" not in response.text
