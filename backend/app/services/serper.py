"""Small, bounded adapter for the Serper search API."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from ..config import Settings

SEARCH_URL = "https://google.serper.dev/search"
SOCIAL_OR_DIRECTORY = {
    "facebook.com", "linkedin.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "tiktok.com", "wikipedia.org", "yelp.com", "crunchbase.com",
    "glassdoor.com", "indeed.com", "yellowpages.com", "mapquest.com",
    "tripadvisor.com", "g2.com", "capterra.com", "zoominfo.com", "news.google.com",
}


class SerperError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass(slots=True)
class SearchEvidence:
    query: str
    knowledge_graph: dict
    organic: list[dict]


@dataclass(slots=True)
class OfficialSite:
    name: str
    website: str
    confidence: float
    evidence: SearchEvidence


def _host(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _blocked(host: str) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in SOCIAL_OR_DIRECTORY)


def _name_tokens(name: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]+", name.lower()) if len(x) > 1}


def _score_result(company: str, item: dict) -> float:
    url = item.get("link") or item.get("url") or ""
    host = _host(url)
    if not host or _blocked(host):
        return -100.0
    tokens = _name_tokens(company)
    host_tokens = set(re.findall(r"[a-z0-9]+", host))
    title = str(item.get("title", "")).lower()
    snippet = str(item.get("snippet", "")).lower()
    score = len(tokens & host_tokens) * 0.32
    if any(t in title for t in tokens):
        score += 0.18
    if any(word in (title + " " + snippet) for word in ("official", "homepage", "about us")):
        score += 0.12
    if urlparse(url).path.strip("/") == "":
        score += 0.12
    return min(score, 1.0)


class SerperClient:
    """Serper adapter using the application's shared HTTPX client."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.calls = 0

    async def search(self, query: str, *, num: int = 10) -> SearchEvidence:
        if not self.settings.serper_api_key:
            raise SerperError("CONFIG_MISSING", "Serper is not configured.", retryable=False)
        if self.calls >= 6:
            raise SerperError("SERPER_LIMIT", "Search limit reached.", retryable=False)
        self.calls += 1
        try:
            response = await self.client.post(
                SEARCH_URL,
                headers={"X-API-KEY": self.settings.serper_api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max(1, min(num, 10))},
                timeout=8.0,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise SerperError("SERPER_UNAVAILABLE", "Search provider did not respond.") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise SerperError("SERPER_UNAVAILABLE", "Search provider is temporarily unavailable.")
        if response.status_code >= 400:
            raise SerperError("SERPER_ERROR", "Search provider rejected the request.", retryable=False)
        try:
            body = response.json()
        except ValueError as exc:
            raise SerperError("SERPER_ERROR", "Search provider returned invalid data.", retryable=False) from exc
        organic = []
        for item in body.get("organic", [])[:8]:
            if isinstance(item, dict) and item.get("link"):
                organic.append({k: str(item.get(k, ""))[:1200] for k in ("title", "link", "snippet")})
        kg = body.get("knowledgeGraph")
        return SearchEvidence(query=query, knowledge_graph=kg if isinstance(kg, dict) else {}, organic=organic)

    async def resolve_official_site(self, company: str) -> OfficialSite | None:
        evidence = await self.search(f"{company} official website", num=10)
        kg = evidence.knowledge_graph
        kg_url = str(kg.get("website") or "")
        if kg_url and _host(kg_url) and not _blocked(_host(kg_url)):
            return OfficialSite(str(kg.get("title") or company)[:160], kg_url, 0.95, evidence)
        best: tuple[float, dict] | None = None
        for item in evidence.organic:
            score = _score_result(company, item)
            if best is None or score > best[0]:
                best = (score, item)
        if best is None or best[0] < 0.42:
            return None
        item = best[1]
        return OfficialSite(str(item.get("title") or company)[:160], str(item["link"]), best[0], evidence)


async def search_serper(client: httpx.AsyncClient, settings: Settings, query: str, *, num: int = 10) -> SearchEvidence:
    return await SerperClient(client, settings).search(query, num=num)


async def resolve_official_site(client: httpx.AsyncClient, settings: Settings, company: str) -> OfficialSite | None:
    return await SerperClient(client, settings).resolve_official_site(company)
