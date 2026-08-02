import json

import httpx
import pytest

from backend.app.schemas import Competitor, ResearchReport
from backend.app.config import Settings
from backend.app.services import crawler
from backend.app.security.url import UnsafeURLError
from backend.app.services.serper import OfficialSite, SearchEvidence
from backend.app.services import research as research_service
from backend.app.services.openrouter import OpenRouterClient, OpenRouterError, parse_json_response


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
        assert payload["model"] == "openrouter/free"
        assert "BEGIN_UNTRUSTED_EVIDENCE" in payload["messages"][1]["content"]
        assert "Acme provides workflow software" in payload["messages"][1]["content"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_report)}}]},
        )

    settings = Settings(openrouter_api_key="test-key", serper_api_key=None)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        report = await research_service.run_research(
            "https://acme.example",
            "openrouter/free",
            client,
            settings,
        )

    assert report.company.name == "Acme"
    assert report.company.website == "https://acme.example/"
    assert report.model_id == "openrouter/free"
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
                "openrouter/free",
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
                        "title": "RivalCo competitor comparison",
                        "link": "https://rivalco.example",
                        "snippet": "RivalCo competes in workflow software.",
                    },
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
            "openrouter/free",
            client,
            settings,
        )

    assert [(item.name, item.website) for item in report.competitors] == [
        ("RivalCo", "https://rivalco.example/")
    ]
    assert all("news.example" not in item.website for item in report.competitors)
    assert all("directory.example" not in item.website for item in report.competitors)


@pytest.mark.asyncio
async def test_name_input_uses_serper_when_crawl_has_no_evidence(monkeypatch):
    async def bypass_dns(value: str) -> str:
        return crawler.normalize_url(value)

    async def empty_crawl(client, root_url, settings):
        return crawler.CrawlResult(
            root_url=root_url,
            warnings=["The site returned no meaningful static HTML."],
        )

    async def fake_search(self, query: str, *, num: int = 10) -> SearchEvidence:
        if "competitors" in query.lower():
            return SearchEvidence(
                query=query,
                knowledge_graph={},
                organic=[
                    {
                        "title": "RivalCo",
                        "link": "https://rivalco.example",
                        "snippet": "A relevant workflow competitor.",
                    }
                ],
            )
        return SearchEvidence(
            query=query,
            knowledge_graph={},
            organic=[
                {
                    "title": "Acme company",
                    "link": "https://acme.example",
                    "snippet": "Acme provides workflow software.",
                }
            ],
        )

    evidence = SearchEvidence(
        query="Acme official website",
        knowledge_graph={},
        organic=[
            {
                "title": "Acme official",
                "link": "https://acme.example",
                "snippet": "The official Acme website.",
            }
        ],
    )

    async def fake_resolve(self, company: str) -> OfficialSite | None:
        return OfficialSite("Acme", "https://acme.example", 0.95, evidence)

    model_report = {
        "company": {
            "name": "Acme",
            "website": "https://acme.example",
            "phone": None,
            "address": None,
            "country": None,
            "industry": None,
        },
        "summary": "Search evidence describes Acme.",
        "products_services": ["Workflow software"],
        "pain_points": [],
        "competitors": [],
        "sources": [],
        "warnings": [],
        "model_id": "ignored-by-service",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_report)}}]},
        )

    monkeypatch.setattr(research_service, "validate_target_url", bypass_dns)
    monkeypatch.setattr(research_service, "crawl_site", empty_crawl)
    monkeypatch.setattr(research_service.SerperClient, "search", fake_search)
    monkeypatch.setattr(research_service.SerperClient, "resolve_official_site", fake_resolve)
    settings = Settings(openrouter_api_key="test-key", serper_api_key="serper-test")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await research_service.run_research(
            "Acme",
            "openrouter/free",
            client,
            settings,
        )

    assert report.summary == "Search evidence describes Acme."


@pytest.mark.asyncio
async def test_direct_url_with_only_competitor_evidence_fails(monkeypatch):
    async def bypass_dns(value: str) -> str:
        return crawler.normalize_url(value)

    async def empty_crawl(client, root_url, settings):
        return crawler.CrawlResult(root_url=root_url)

    async def unavailable_search(self, query: str, *, num: int = 10) -> SearchEvidence:
        if "competitors" in query.lower():
            return SearchEvidence(
                query=query,
                knowledge_graph={},
                organic=[
                    {
                        "title": "Competitor article",
                        "link": "https://news.example/acme-competitors",
                        "snippet": "Competitor discussion only.",
                    }
                ],
            )
        raise research_service.SerperError(
            "SERPER_UNAVAILABLE",
            "Search provider unavailable.",
        )
    monkeypatch.setattr(research_service, "validate_target_url", bypass_dns)
    monkeypatch.setattr(research_service, "crawl_site", empty_crawl)
    monkeypatch.setattr(research_service.SerperClient, "search", unavailable_search)
    settings = Settings(openrouter_api_key="test-key", serper_api_key="serper-test")

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(research_service.ResearchServiceError) as caught:
            await research_service.run_research(
                "https://acme.example",
                "openrouter/free",
                client,
                settings,
            )

    assert caught.value.code == "INSUFFICIENT_EVIDENCE"


@pytest.mark.asyncio
async def test_empty_competitor_evidence_does_not_resolve_model_name(monkeypatch):
    calls: list[str] = []

    async def fake_resolve(self, company: str) -> OfficialSite | None:
        calls.append(company)
        return OfficialSite(
            company,
            "https://resolved.example",
            0.9,
            SearchEvidence(query=f"{company} official website", knowledge_graph={}, organic=[]),
        )

    monkeypatch.setattr(research_service.SerperClient, "resolve_official_site", fake_resolve)
    evidence = SearchEvidence(query="Acme competitors", knowledge_graph={}, organic=[])
    proposed = [Competitor(name="RivalCo", website="https://article.example", fit="Candidate")]

    async with httpx.AsyncClient() as client:
        serper = research_service.SerperClient(client, Settings(serper_api_key="key"))
        resolved, warnings = await research_service._resolve_report_competitors(
            proposed,
            serper=serper,
            root_url="https://acme.example/",
            candidate_evidence=evidence,
            can_resolve=True,
        )

    assert resolved == []
    assert calls == []
    assert warnings == ["Competitor discovery returned no candidate evidence."]


@pytest.mark.asyncio
async def test_unrelated_model_name_is_not_resolved(monkeypatch):
    calls: list[str] = []

    async def fake_resolve(self, company: str) -> OfficialSite | None:
        calls.append(company)
        return OfficialSite(
            company,
            "https://resolved.example",
            0.9,
            SearchEvidence(query=f"{company} official website", knowledge_graph={}, organic=[]),
        )

    monkeypatch.setattr(research_service.SerperClient, "resolve_official_site", fake_resolve)
    evidence = SearchEvidence(
        query="Acme competitors",
        knowledge_graph={},
        organic=[
            {
                "title": "RivalCo competitor comparison",
                "link": "https://rivalco.example",
                "snippet": "RivalCo serves the same market.",
            }
        ],
    )
    proposed = [Competitor(name="UnrelatedCorp", website="https://unrelated.example", fit="Candidate")]

    async with httpx.AsyncClient() as client:
        serper = research_service.SerperClient(client, Settings(serper_api_key="key"))
        resolved, warnings = await research_service._resolve_report_competitors(
            proposed,
            serper=serper,
            root_url="https://acme.example/",
            candidate_evidence=evidence,
            can_resolve=True,
        )

    assert resolved == []
    assert calls == []
    assert warnings == ["Proposed competitor names were not present in competitor evidence."]


@pytest.mark.asyncio
async def test_openrouter_client_blocks_paid_model_before_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("paid model reached OpenRouter")

    settings = Settings(openrouter_api_key="test-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenRouterClient(client, settings)
        with pytest.raises(OpenRouterError) as caught:
            await adapter._call("openai/gpt-5", "test prompt")

    assert caught.value.code == "MODEL_NOT_ALLOWED"


def test_parse_json_response_extracts_report_object_from_model_preamble():
    value = "I will provide the report now.\n{\"company\": {}, \"summary\": \"Valid\"}\nDone."

    assert parse_json_response(value)["summary"] == "Valid"


@pytest.mark.asyncio
async def test_invalid_json_falls_back_to_another_free_model(monkeypatch):
    async def bypass_dns(value: str) -> str:
        return crawler.normalize_url(value)

    async def fake_crawl(client, root_url, settings):
        return crawler.CrawlResult(
            root_url=root_url,
            page_text="Acme builds workflow software.",
            sources=[{"title": "Acme home", "url": root_url, "source_type": "website"}],
        )

    class FlakyAdapter:
        calls: list[tuple[str, bool]] = []

        def __init__(self, client, settings):
            pass

        async def analyze(self, model_id, evidence, *, corrective=False):
            self.calls.append((model_id, corrective))
            if len(self.calls) < 2:
                raise OpenRouterError("MODEL_OUTPUT_INVALID", "invalid JSON")
            return ResearchReport.model_validate(
                {
                    "company": {
                        "name": "Acme",
                        "website": "https://acme.example",
                        "phone": None,
                        "address": None,
                        "country": None,
                        "industry": "Software",
                    },
                    "summary": "Valid report.",
                    "products_services": ["Workflow software"],
                    "pain_points": [],
                    "competitors": [],
                    "sources": [],
                    "warnings": [],
                    "model_id": model_id,
                }
            )

    monkeypatch.setattr(research_service, "validate_target_url", bypass_dns)
    monkeypatch.setattr(research_service, "crawl_site", fake_crawl)
    monkeypatch.setattr(research_service, "OpenRouterClient", FlakyAdapter)
    settings = Settings(
        _env_file=None,
        openrouter_api_key="test-key",
        serper_api_key=None,
    )

    async with httpx.AsyncClient() as client:
        report = await research_service.run_research(
            "https://acme.example",
            "openai/gpt-oss-20b:free",
            client,
            settings,
        )

    assert settings.effective_default_model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert settings.model_suggestions[:2] == [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "openai/gpt-oss-20b:free",
    ]
    assert report.model_id == "nvidia/nemotron-3-super-120b-a12b:free"
    assert FlakyAdapter.calls == [
        ("openai/gpt-oss-20b:free", False),
        ("nvidia/nemotron-3-super-120b-a12b:free", False),
    ]


@pytest.mark.asyncio
async def test_company_name_timeout_fallback_is_bounded(monkeypatch):
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

    class TimeoutAdapter:
        calls: list[tuple[str, bool]] = []

        def __init__(self, client, settings):
            pass

        async def analyze(self, model_id, evidence, *, corrective=False):
            self.calls.append((model_id, corrective))
            raise OpenRouterError("OPENROUTER_TIMEOUT", "timed out", retryable=True)

    monkeypatch.setattr(research_service, "validate_target_url", bypass_dns)
    monkeypatch.setattr(research_service, "crawl_site", fake_crawl)
    monkeypatch.setattr(research_service.SerperClient, "resolve_official_site", fake_resolve)
    monkeypatch.setattr(research_service.SerperClient, "search", fake_search)
    monkeypatch.setattr(research_service, "OpenRouterClient", TimeoutAdapter)
    settings = Settings(
        openrouter_api_key="test-key",
        serper_api_key="serper-test",
        openrouter_model_suggestions=(
            "openai/gpt-oss-20b:free,"
            "nvidia/nemotron-3-super-120b-a12b:free,"
            "openrouter/free"
        ),
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(research_service.ResearchServiceError) as caught:
            await research_service.run_research(
                "Acme",
                "openai/gpt-oss-20b:free",
                client,
                settings,
            )

    assert caught.value.code == "OPENROUTER_TIMEOUT"
    assert TimeoutAdapter.calls == [
        ("openai/gpt-oss-20b:free", False),
        ("nvidia/nemotron-3-super-120b-a12b:free", False),
    ]


@pytest.mark.asyncio
async def test_length_finished_model_output_is_retryable_truncation():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 2000
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": None},
                    }
                ]
            },
        )

    settings = Settings(openrouter_api_key="test-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenRouterClient(client, settings)
        with pytest.raises(OpenRouterError) as caught:
            await adapter._call("openai/gpt-oss-20b:free", "test prompt")

    assert caught.value.code == "MODEL_OUTPUT_TRUNCATED"
    assert caught.value.retryable is True

@pytest.mark.asyncio
async def test_complete_json_with_length_finish_reason_is_accepted():
    content = json.dumps({"summary": "complete"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": content},
                    }
                ]
            },
        )

    settings = Settings(openrouter_api_key="test-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenRouterClient(client, settings)
        assert await adapter._call("openai/gpt-oss-20b:free", "test prompt") == content