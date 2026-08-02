"""Bounded research pipeline joining crawler, Serper, and OpenRouter."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Awaitable, Callable

import httpx

from ..config import Settings
from ..security.url import UnsafeURLError
from ..schemas import Competitor, ProgressEvent, ResearchReport, Source
from .openrouter import OpenRouterClient, OpenRouterError
from .serper import SearchEvidence, SerperClient, SerperError

try:
    from .crawler import crawl_site, normalize_url, validate_target_url
except ImportError:  # allows importing service before optional crawler package is installed
    crawl_site = None
    def normalize_url(value: str) -> str:
        return value
    async def validate_target_url(value: str) -> str:
        return value


class ResearchServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False, status_code: int = 422):
        super().__init__(message)
        self.code, self.message, self.retryable, self.status_code = code, message, retryable, status_code


ProgressCallback = Callable[[ProgressEvent], Awaitable[None] | None]


def _is_url(query: str) -> bool:
    value = query.strip()
    if value.lower().startswith(("http://", "https://")):
        return True
    return bool(re.fullmatch(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?::\d+)?(?:/[^\s]*)?", value))


def _normalize_input(query: str) -> str:
    value = query.strip()
    if _is_url(value) and not value.lower().startswith(("http://", "https://")):
        value = "https://" + value
    return value


def _evidence_search(item: SearchEvidence) -> list[dict[str, str]]:
    values = []
    for row in item.organic[:8]:
        values.append({"title": str(row.get("title", ""))[:240], "url": str(row.get("link", ""))[:2048], "snippet": str(row.get("snippet", ""))[:800]})
    if item.knowledge_graph:
        values.insert(0, {"title": str(item.knowledge_graph.get("title", "Knowledge Graph"))[:240], "url": str(item.knowledge_graph.get("website", ""))[:2048], "snippet": str(item.knowledge_graph.get("description", ""))[:800]})
    return values


def _crawler_parts(result: Any) -> tuple[dict[str, Any], str, list[dict[str, Any]], list[str]]:
    facts = getattr(result, "company_facts", None) or getattr(result, "facts", None) or {}
    text = getattr(result, "page_text", None) or getattr(result, "text", None) or getattr(result, "extracted_text", None) or ""
    sources = getattr(result, "sources", None) or []
    warnings = list(getattr(result, "warnings", None) or [])
    return dict(facts), str(text)[:25000], list(sources)[:15], warnings[:10]


async def _emit(callback: ProgressCallback | None, stage: str, percent: int, message: str) -> None:
    if callback:
        event = ProgressEvent(stage=stage, percent=percent, message=message)
        result = callback(event)
        if asyncio.iscoroutine(result):
            await result
async def _resolve_report_competitors(
    proposed: list[Competitor],
    *,
    serper: SerperClient,
    root_url: str,
    can_resolve: bool,
) -> tuple[list[Competitor], list[str]]:
    """Resolve model-proposed names to safe official sites in parallel."""
    proposals: list[Competitor] = []
    seen_names: set[str] = set()
    for competitor in proposed[:3]:
        key = competitor.name.casefold().strip()
        if key and key not in seen_names:
            seen_names.add(key)
            proposals.append(competitor)
    if not proposals:
        return [], []
    if not can_resolve:
        return [], ["Competitor websites could not be verified from public search evidence."]

    root_host = urlparse(root_url).hostname

    async def resolve_one(candidate: Competitor) -> Competitor | None:
        try:
            official = await serper.resolve_official_site(candidate.name)
            if official is None:
                return None
            safe = await validate_target_url(official.website)
            website = normalize_url(safe)
            if urlparse(website).hostname == root_host:
                return None
            return candidate.model_copy(update={"website": website})
        except Exception:
            return None

    resolved = await asyncio.gather(*(resolve_one(candidate) for candidate in proposals))
    verified: list[Competitor] = []
    verified_names: set[str] = set()
    seen_urls: set[str] = set()
    for candidate in resolved:
        if candidate is None:
            continue
        name_key = candidate.name.casefold()
        url_key = candidate.website.casefold()
        if name_key in verified_names or url_key in seen_urls:
            continue
        verified_names.add(name_key)
        seen_urls.add(url_key)
        verified.append(candidate)
    warnings = (
        ["Some proposed competitors could not be verified and were omitted."]
        if len(verified) < len(proposals)
        else []
    )
    return verified, warnings



async def run_research(
    query: str,
    model_id: str,
    client: httpx.AsyncClient,
    settings: Settings,
    progress: ProgressCallback | None = None,
) -> ResearchReport:
    """Run one complete bounded research job. Callers enforce the global deadline."""
    query = query.strip()
    if not settings.openrouter_api_key:
        raise ResearchServiceError("CONFIG_MISSING", "Research providers are not configured.", status_code=503)
    direct = _is_url(query)
    root_url: str
    company_name = query
    serper = SerperClient(client, settings)
    search_evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    competitor_search_evidence: SearchEvidence | None = None

    await _emit(progress, "resolving", 10, "Finding the official website")
    if direct:
        root_url = _normalize_input(query)
        try:
            root_url = await validate_target_url(root_url)
            root_url = normalize_url(root_url)
        except Exception as exc:
            raise ResearchServiceError("UNSAFE_URL", "The supplied URL is not safe to fetch.", status_code=403) from exc
        parsed_host = urlparse(root_url).hostname or ""
        company_name = parsed_host.removeprefix("www.").split(".")[0].replace("-", " ").title()
    else:
        if not settings.serper_api_key:
            raise ResearchServiceError("CONFIG_MISSING", "Research providers are not configured.", status_code=503)
        try:
            official = await serper.resolve_official_site(query)
        except SerperError as exc:
            raise ResearchServiceError(exc.code, exc.message, retryable=exc.retryable, status_code=503 if exc.code == "SERPER_UNAVAILABLE" else 422) from exc
        if official is None:
            raise ResearchServiceError("OFFICIAL_SITE_NOT_FOUND", "We could not confidently find the official website. Please resubmit with a URL.", status_code=404)
        try:
            root_url = await validate_target_url(official.website)
            root_url = normalize_url(root_url)
        except Exception as exc:
            raise ResearchServiceError(
                "OFFICIAL_SITE_NOT_FOUND",
                "We could not confidently find a safe official website. Please resubmit with a URL.",
                status_code=404,
            ) from exc
        company_name = official.name or query
        search_evidence.append({"query": official.evidence.query, "results": _evidence_search(official.evidence)})

    if crawl_site is None:
        raise ResearchServiceError("CRAWLER_UNAVAILABLE", "Website crawler is unavailable.", retryable=True, status_code=503)
    await _emit(progress, "crawling", 30, "Reading important website pages")
    try:
        crawl = await crawl_site(client, root_url, settings)
    except UnsafeURLError as exc:
        raise ResearchServiceError(
            "UNSAFE_URL",
            "The website redirected to an unsafe address.",
            status_code=403,
        ) from exc
    except Exception:
        warnings.append("Some website pages could not be read.")
        crawl = None
    facts, page_text, website_sources, crawl_warnings = _crawler_parts(crawl) if crawl is not None else ({}, "", [], [])
    warnings.extend(crawl_warnings)
    if not page_text and not website_sources and not direct:
        raise ResearchServiceError("INSUFFICIENT_EVIDENCE", "The official website did not provide enough evidence.", status_code=422)

    await _emit(progress, "searching", 55, "Checking public sources and competitors")
    if settings.serper_api_key:
        async def search_optional(text: str) -> SearchEvidence | None:
            try:
                return await serper.search(text, num=10)
            except SerperError:
                return None
        enrich_q = f"{company_name} headquarters phone products services"
        competitor_q = f"{company_name} competitors {facts.get('country', '')}".strip()
        enriched, competitors_search = await asyncio.gather(search_optional(enrich_q), search_optional(competitor_q))
        if enriched:
            search_evidence.append({"query": enriched.query, "results": _evidence_search(enriched)})
            kg = enriched.knowledge_graph
            for key in ("phone", "address", "country", "industry"):
                if kg.get(key) and not facts.get(key):
                    facts[key] = str(kg[key])[:400]
        else:
            warnings.append("Public search enrichment was unavailable; using website evidence.")
        if competitors_search:
            search_evidence.append({"query": competitors_search.query, "results": _evidence_search(competitors_search)})
            competitor_search_evidence = competitors_search
        else:
            warnings.append("Competitor discovery was unavailable.")
    elif direct:
        warnings.append("Public search enrichment was unavailable; using website evidence.")


    await _emit(progress, "analyzing", 75, "Generating structured insights")
    evidence = {
        "company_name": company_name,
        "official_website": root_url,
        "company_facts": facts,
        "website_pages": page_text,
        "website_sources": website_sources,
        "search_results": search_evidence,
    }
    async def analyze_with_retry() -> ResearchReport:
        adapter = OpenRouterClient(client, settings)
        try:
            return await adapter.analyze(model_id, evidence)
        except OpenRouterError as first:
            if first.code == "MODEL_OUTPUT_INVALID":
                try:
                    return await adapter.analyze(model_id, evidence, corrective=True)
                except OpenRouterError as second:
                    first = second
            elif first.retryable:
                try:
                    return await adapter.analyze(model_id, evidence)
                except OpenRouterError as second:
                    first = second
            raise ResearchServiceError(
                first.code,
                first.message,
                retryable=first.retryable,
                status_code=503 if first.retryable else 422,
            ) from first

    report = await analyze_with_retry()

    company = report.company.model_copy(update={"name": company_name, "website": root_url})
    deterministic_sources = []
    for source in website_sources[:15]:
        try:
            deterministic_sources.append(Source.model_validate(source))
        except Exception:
            continue
    merged_sources = deterministic_sources + report.sources
    seen_urls: set[str] = set()
    unique_sources: list[Source] = []
    for source in merged_sources:
        if source.url not in seen_urls:
            seen_urls.add(source.url)
            unique_sources.append(source)
    resolved_competitors, competitor_warnings = await _resolve_report_competitors(
        report.competitors,
        serper=serper,
        root_url=root_url,
        can_resolve=bool(settings.serper_api_key and competitor_search_evidence),
    )
    warnings.extend(competitor_warnings)
    await _emit(progress, "finalizing", 95, "Validating the report")
    report = report.model_copy(update={
        "company": company,
        "competitors": resolved_competitors[:5],
        "sources": unique_sources[:15],
        "warnings": list(dict.fromkeys(warnings + report.warnings))[:10],
        "generated_at": datetime.now(timezone.utc),
        "model_id": model_id,
    })
    return ResearchReport.model_validate(report)
