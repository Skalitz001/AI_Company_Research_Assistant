import json

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import app
from backend.app.schemas import ProgressEvent, ResearchReport
from backend.app.routers import research as research_router


def test_research_route_streams_progress_and_result(monkeypatch):
    settings = Settings(
        serper_api_key="serper-test",
        openrouter_api_key="openrouter-test",
        openrouter_default_model="openrouter/example-model",
    )
    report = ResearchReport.model_validate(
        {
            "company": {
                "name": "Acme",
                "website": "https://acme.example",
                "phone": None,
                "address": None,
                "country": "US",
                "industry": "Software",
            },
            "summary": "A concise summary.",
            "products_services": ["Workflow software"],
            "pain_points": ["A hypothesis"],
            "competitors": [],
            "sources": [
                {"title": "Acme", "url": "https://acme.example", "source_type": "website"}
            ],
            "warnings": [],
            "model_id": "openrouter/example-model",
        }
    )

    async def fake_research(query, model_id, client, settings, progress):
        await progress(ProgressEvent(stage="resolving", percent=10, message="Finding the official website"))
        return report

    monkeypatch.setattr(research_router, "get_settings", lambda: settings)
    monkeypatch.setattr(research_router, "run_research", fake_research)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/research",
            json={"query": "Acme", "model_id": "openrouter/example-model"},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[0]["type"] == "progress"
    assert events[-1]["type"] == "result"
    assert events[-1]["report"]["company"]["name"] == "Acme"



def test_direct_url_research_does_not_require_serper(monkeypatch):
    settings = Settings(
        serper_api_key=None,
        openrouter_api_key="openrouter-test",
        openrouter_default_model="openrouter/example-model",
    )
    report = ResearchReport.model_validate(
        {
            "company": {
                "name": "Acme",
                "website": "https://acme.example",
                "phone": None,
                "address": None,
                "country": "US",
                "industry": "Software",
            },
            "summary": "Crawled direct URL evidence.",
            "products_services": ["Workflow software"],
            "pain_points": ["A hypothesis"],
            "competitors": [],
            "sources": [
                {"title": "Acme", "url": "https://acme.example", "source_type": "website"}
            ],
            "warnings": [],
            "model_id": "openrouter/example-model",
        }
    )
    calls = []

    async def fake_research(query, model_id, client, received_settings, progress):
        calls.append((query, model_id, received_settings.serper_api_key))
        return report

    monkeypatch.setattr(research_router, "get_settings", lambda: settings)
    monkeypatch.setattr(research_router, "run_research", fake_research)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/research",
            json={"query": "https://acme.example", "model_id": "openrouter/example-model"},
        )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[-1]["type"] == "result"
    assert calls == [("https://acme.example", "openrouter/example-model", None)]