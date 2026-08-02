import json
import asyncio
import time

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import app
from backend.app.schemas import ProgressEvent, ResearchReport
from backend.app.routers import research as research_router
from backend.app.services import crawler
from backend.app.services import research as research_service
from backend.app.services.serper import OfficialSite, SearchEvidence


def test_research_route_streams_progress_and_result(monkeypatch):
    settings = Settings(
        serper_api_key="serper-test",
        openrouter_api_key="openrouter-test",
        openrouter_default_model="openrouter/free",
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
            "model_id": "openrouter/free",
        }
    )

    async def fake_research(query, model_id, client, settings, progress, deadline=None):
        await progress(ProgressEvent(stage="resolving", percent=10, message="Finding the official website"))
        return report

    monkeypatch.setattr(research_router, "get_settings", lambda: settings)
    monkeypatch.setattr(research_router, "run_research", fake_research)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/research",
            json={"query": "Acme", "model_id": "openrouter/free"},
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
        openrouter_default_model="openrouter/free",
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
            "model_id": "openrouter/free",
        }
    )
    calls = []

    async def fake_research(query, model_id, client, received_settings, progress, deadline=None):
        calls.append((query, model_id, received_settings.serper_api_key))
        return report

    monkeypatch.setattr(research_router, "get_settings", lambda: settings)
    monkeypatch.setattr(research_router, "run_research", fake_research)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/research",
            json={"query": "https://acme.example", "model_id": "openrouter/free"},
        )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[-1]["type"] == "result"
    assert calls == [("https://acme.example", "openrouter/free", None)]


def test_paid_model_is_rejected_before_provider_call(monkeypatch):
    settings = Settings(
        serper_api_key="serper-test",
        openrouter_api_key="openrouter-test",
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("paid model reached the research pipeline")

    monkeypatch.setattr(research_router, "get_settings", lambda: settings)
    monkeypatch.setattr(research_router, "run_research", should_not_run)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/research",
            json={"query": "Acme", "model_id": "openai/gpt-5"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MODEL_NOT_ALLOWED"


def test_company_name_model_timeout_is_bounded_through_route(monkeypatch):
    settings = Settings(
        serper_api_key="serper-test",
        openrouter_api_key="openrouter-test",
        openrouter_model_suggestions=(
            "openai/gpt-oss-20b:free,"
            "nvidia/nemotron-3-super-120b-a12b:free,"
            "openrouter/free"
        ),
    )

    async def bypass_dns(value: str) -> str:
        return crawler.normalize_url(value)

    async def fake_resolve(self, company: str) -> OfficialSite:
        evidence = SearchEvidence(
            query=f"{company} official website",
            knowledge_graph={"title": company, "website": "https://acme.example"},
            organic=[],
        )
        return OfficialSite(company, "https://acme.example", 0.95, evidence)

    async def fake_search(self, query: str, *, num: int = 10) -> SearchEvidence:
        return SearchEvidence(
            query=query,
            knowledge_graph={"title": "Acme", "website": "https://acme.example"},
            organic=[],
        )

    async def fake_crawl(client, root_url, settings):
        return crawler.CrawlResult(
            root_url=root_url,
            company_facts={"industry": "Software"},
            page_text="Acme builds workflow software.",
            sources=[{"title": "Acme home", "url": root_url, "source_type": "website"}],
        )

    calls: list[tuple[str, bool]] = []

    class DelayedAdapter:
        def __init__(self, client, settings):
            pass

        async def analyze(self, model_id, evidence, *, corrective=False):
            calls.append((model_id, corrective))
            await asyncio.sleep(0.2)

    monkeypatch.setattr(research_router, "get_settings", lambda: settings)
    monkeypatch.setattr(research_service, "validate_target_url", bypass_dns)
    monkeypatch.setattr(research_service, "crawl_site", fake_crawl)
    monkeypatch.setattr(research_service.SerperClient, "resolve_official_site", fake_resolve)
    monkeypatch.setattr(research_service.SerperClient, "search", fake_search)
    monkeypatch.setattr(research_service, "OpenRouterClient", DelayedAdapter)
    monkeypatch.setattr(research_service, "MODEL_ATTEMPT_TIMEOUT_SECONDS", 0.05)

    with TestClient(app) as client:
        started = time.perf_counter()
        response = client.post(
            "/api/v1/research",
            json={"query": "Acme", "model_id": "openai/gpt-oss-20b:free"},
        )
        elapsed = time.perf_counter() - started

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]["code"] == "OPENROUTER_TIMEOUT"
    assert calls == [
        ("openai/gpt-oss-20b:free", False),
        ("nvidia/nemotron-3-super-120b-a12b:free", False),
    ]
    assert elapsed < 2