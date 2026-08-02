import json

import httpx
import pytest

from backend.app.config import Settings
from backend.app.services import crawler
from backend.app.security.url import UnsafeURLError
from backend.app.services.serper import OfficialSite, SearchEvidence
from backend.app.services import research as research_service


@pytest.mark.asyncio
async def test_direct_url_research_uses_async_safe_validation_and_exact_model(monkeypatch):
    async def bypass_dns(value: str) -> str:
        return crawler.normalize_url(value)

    async def fake_crawl(client, root_url, settings):
        return crawler.CrawlResult(
            root_url=root_url,
            company_facts={"country": "United States", "industry": "Software"},
            page_text="Acme provides workflow software for small teams.",
            sources=[{"title": "Acme home", "url": root_url, "source_type": "website"}],
        )

    monkeypatch.setattr(research_service, "validate_target_url", bypass_dns)
    monkeypatch.setattr(research_service, "crawl_site", fake_crawl)

    model_report = {
        "company": {
            "name": "Wrong model name",
            "website": "https://wrong.example",
            "phone": None,
            "address": None,
            "country": "United States",
            "industry": "Software",
        },
        "summary": "Acme provides workflow software.",
        "products_services": ["Workflow software"],
        "pain_points": ["Teams may need simpler automation."],
        "competitors": [
            {
                "name": "Rival",
                "website": "https://rival.example",
                "fit": "Same software category",
            }
        ],
        "sources": [],
        "warnings": [],
        "model_id": "ignored-by-service",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "openrouter/example-model"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_report)}}]},
        )

    settings = Settings(openrouter_api_key="test-key", serper_api_key=None)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        report = await research_service.run_research(
            "https://acme.example",
            "openrouter/example-model",
            client,
            settings,
        )

    assert report.company.name == "Acme"
    assert report.company.website == "https://acme.example/"
    assert report.model_id == "openrouter/example-model"
    assert report.competitors == []
    assert report.sources[0].url == "https://acme.example/"



@pytest.mark.asyncio
async def test_unsafe_redirect_becomes_structured_error(monkeypatch):
    async def bypass_dns(value: str) -> str:
        return crawler.normalize_url(value)

    async def unsafe_crawl(client, root_url, settings):
        raise UnsafeURLError("redirected to private address")

    monkeypatch.setattr(research_service, "validate_target_url", bypass_dns)
    monkeypatch.setattr(research_service, "crawl_site", unsafe_crawl)
    settings = Settings(openrouter_api_key="test-key", serper_api_key=None)

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(research_service.ResearchServiceError) as caught:
            await research_service.run_research(
                "https://acme.example",
                "openrouter/example-model",
                client,
                settings,
            )

    assert caught.value.code == "UNSAFE_URL"


@pytest.mark.asyncio
async def test_search_articles_cannot_become_competitor_websites(monkeypatch):
    async def bypass_dns(value: str) -> str:
        return crawler.normalize_url(value)

    async def fake_crawl(client, root_url, settings):
        return crawler.CrawlResult(
            root_url=root_url,
            page_text="Acme builds workflow software.",
            sources=[{"title": "Acme home", "url": root_url, "source_type": "website"}],
        )

    async def fake_search(self, query: str, *, num: int = 10) -> SearchEvidence:
        if "competitors" in query.lower():
            return SearchEvidence(
                query=query,
                knowledge_graph={},
                organic=[
                    {
                        "title": "Acme competitors article",
                        "link": "https://news.example/acme-competitors",
                        "snippet": "An article about competitors.",
                    },
                    {
                        "title": "Acme listing",
                        "link": "https://directory.example/acme",
                        "snippet": "A directory listing.",
                    },
                ],
            )
        return SearchEvidence(query=query, knowledge_graph={}, organic=[])

    async def fake_resolve(self, company: str) -> OfficialSite | None:
        evidence = SearchEvidence(query=f"{company} official website", knowledge_graph={}, organic=[])
        if company.casefold() == "rivalco":
            return OfficialSite("RivalCo", "https://rivalco.example", 0.9, evidence)
        if company.casefold() == "acme":
            return OfficialSite("Acme", "https://acme.example", 0.9, evidence)
        return None

    model_report = {
        "company": {
            "name": "Acme",
            "website": "https://acme.example",
            "phone": None,
            "address": None,
            "country": "United States",
            "industry": "Software",
        },
        "summary": "Acme builds workflow software.",
        "products_services": ["Workflow software"],
        "pain_points": ["Teams may need simpler automation."],
        "competitors": [
            {
                "name": "RivalCo",
                "website": "https://news.example/rivalco-article",
                "fit": "Same software category",
            },
            {
                "name": "Acme",
                "website": "https://acme.example",
                "fit": "The company itself, not a competitor",
            },
        ],
        "sources": [],
        "warnings": [],
        "model_id": "ignored-by-service",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "openrouter.ai"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_report)}}]},
        )

    monkeypatch.setattr(research_service, "validate_target_url", bypass_dns)
    monkeypatch.setattr(research_service, "crawl_site", fake_crawl)
    monkeypatch.setattr(research_service.SerperClient, "search", fake_search)
    monkeypatch.setattr(research_service.SerperClient, "resolve_official_site", fake_resolve)
    settings = Settings(openrouter_api_key="test-key", serper_api_key="serper-test")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await research_service.run_research(
            "https://acme.example",
            "openrouter/example-model",
            client,
            settings,
        )

    assert [(item.name, item.website) for item in report.competitors] == [
        ("RivalCo", "https://rivalco.example/")
    ]
    assert all("news.example" not in item.website for item in report.competitors)
    assert all("directory.example" not in item.website for item in report.competitors)