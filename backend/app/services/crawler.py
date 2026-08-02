"""Bounded, static-HTML, SSRF-safe website crawler."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from ..security.url import UnsafeURLError, inspect_url, normalize_url, validate_target_url


PAGE_TIMEOUT_SECONDS = 6.0
AGGREGATE_TIMEOUT_SECONDS = 15.0
MAX_REDIRECTS = 3
MAX_PAGES = 6
MAX_PAGE_BYTES = 1_048_576
MAX_PAGE_CHARS = 5_000
MAX_TOTAL_CHARS = 25_000
MAX_ROBOTS_BYTES = 256 * 1024

_SKIP_PATH_PARTS = frozenset(
    {
        "login",
        "signin",
        "sign-in",
        "signup",
        "sign-up",
        "auth",
        "account",
        "cart",
        "checkout",
        "search",
        "privacy",
        "terms",
        "legal",
        "cookie",
        "cookies",
        "careers",
        "career",
        "jobs",
        "job",
        "blog",
        "news",
    }
)
_SKIP_EXTENSIONS = frozenset(
    {
        ".7z",
        ".avi",
        ".bmp",
        ".csv",
        ".doc",
        ".docx",
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".mp3",
        ".mp4",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".svg",
        ".tar",
        ".tgz",
        ".tif",
        ".ttf",
        ".txt",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".xls",
        ".xlsx",
        ".xml",
        ".zip",
    }
)
_LINK_TERMS = {
    "about": 7,
    "product": 6,
    "products": 6,
    "service": 6,
    "services": 6,
    "solution": 5,
    "solutions": 5,
    "contact": 5,
    "pricing": 4,
    "company": 3,
}


@dataclass(frozen=True)
class CrawledPage:
    url: str
    title: str
    description: str
    text: str
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrawlResult:
    """Stable crawler evidence returned to the research orchestration layer."""

    root_url: str
    company_facts: dict[str, Any] = field(default_factory=dict)
    page_text: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pages: list[CrawledPage] = field(default_factory=list)

    @property
    def extracted_text(self) -> str:
        return self.page_text

    @property
    def text(self) -> str:
        return self.page_text


@dataclass(frozen=True)
class _FetchedPage:
    url: str
    content: bytes
    content_type: str


class CrawlError(RuntimeError):
    """Internal error for a page that should become a crawl warning."""


def _setting(settings: Any, name: str, default: Any) -> Any:
    return getattr(settings, name, default)


def _same_host(left: str, right: str) -> bool:
    try:
        return inspect_url(left).host == inspect_url(right).host
    except UnsafeURLError:
        return False


def _skip_url(url: str, root_url: str) -> bool:
    try:
        target = inspect_url(url)
        root = inspect_url(root_url)
    except UnsafeURLError:
        return True
    path = urlsplit(target.url).path
    parts = {part.casefold() for part in path.split("/") if part}
    if parts & _SKIP_PATH_PARTS:
        return True
    lower_path = path.casefold()
    if any(lower_path.endswith(extension) for extension in _SKIP_EXTENSIONS):
        return True
    return False


def _link_score(url: str, label: str) -> int:
    haystack = f"{urlsplit(url).path} {label}".casefold()
    score = sum(weight for term, weight in _LINK_TERMS.items() if re.search(rf"\b{re.escape(term)}\b", haystack))
    # A very deep path is less likely to be a concise company-information page.
    score -= max(0, len([part for part in urlsplit(url).path.split("/") if part]) - 2)
    return score


def _clean_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _bounded_text(value: str, limit: int = MAX_PAGE_CHARS) -> str:
    value = _clean_text(value)
    if len(value) <= limit:
        return value
    clipped = value[:limit]
    # Avoid ending in the middle of an entity/word where possible.
    return clipped.rsplit(" ", 1)[0] if " " in clipped else clipped


def _jsonld_objects(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _jsonld_objects(item)
    elif isinstance(value, dict):
        if "@graph" in value:
            yield from _jsonld_objects(value["@graph"])
        yield value


def _value(value: Any) -> str | None:
    if isinstance(value, str):
        return _clean_text(value) or None
    return None


def _address_value(address: Any) -> str | None:
    if isinstance(address, str):
        return _clean_text(address) or None
    if not isinstance(address, dict):
        return None
    fields = (
        address.get("streetAddress"),
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("postalCode"),
        address.get("addressCountry"),
    )
    result = ", ".join(_clean_text(str(item)) for item in fields if item)
    return result or None


def _extract_page(url: str, html: bytes) -> CrawledPage:
    soup = BeautifulSoup(html, "lxml")
    title = _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    description_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    description = _clean_text(description_tag.get("content", "")) if description_tag else ""

    facts: dict[str, Any] = {"title": title, "description": description}
    phones: list[str] = []
    emails: list[str] = []
    jsonld: list[dict[str, Any]] = []
    for script in soup.find_all("script"):
        if str(script.get("type", "")).casefold() != "application/ld+json":
            continue
        try:
            parsed = json.loads(script.string or script.get_text())
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        jsonld.extend(item for item in _jsonld_objects(parsed) if isinstance(item, dict))
    for obj in jsonld:
        kinds = obj.get("@type", [])
        if isinstance(kinds, str):
            kinds = [kinds]
        kinds = {str(kind).casefold() for kind in kinds}
        if "organization" in kinds or kinds & {"localbusiness", "corporation", "brand"}:
            for key in ("name", "telephone", "email", "description", "industry"):
                item = _value(obj.get(key))
                if item and key not in facts:
                    facts[key] = item
                elif item and key in {"telephone", "email"}:
                    facts[key] = facts.get(key) or item
            address = _address_value(obj.get("address"))
            if address:
                facts.setdefault("address", address)
            country = obj.get("address", {}).get("addressCountry") if isinstance(obj.get("address"), dict) else None
            if country:
                facts.setdefault("country", _value(country))
        if "postaladdress" in kinds:
            address = _address_value(obj)
            if address:
                facts.setdefault("address", address)
        if "contactpoint" in kinds:
            phone = _value(obj.get("telephone"))
            email = _value(obj.get("email"))
            if phone:
                phones.append(phone)
            if email:
                emails.append(email)

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        scheme = urlsplit(href).scheme.casefold()
        if scheme == "tel":
            number = _clean_text(href[4:])
            if number:
                phones.append(number)
        elif scheme == "mailto":
            address = _clean_text(href[7:].split("?", 1)[0])
            if address:
                emails.append(address)

    if phones:
        facts["phone"] = next(iter(dict.fromkeys(phones)))
    elif facts.get("telephone"):
        facts["phone"] = facts["telephone"]
    if emails:
        facts["email"] = next(iter(dict.fromkeys(emails)))
    elif facts.get("email"):
        facts["email"] = facts["email"]

    # Remove non-content and recurring site chrome before extracting evidence.
    for element in soup.find_all(["script", "style", "svg", "form", "nav", "footer", "noscript"]):
        element.decompose()
    for element in soup.find_all(True):
        marker = " ".join(
            [str(element.get("id", "")), " ".join(str(item) for item in element.get("class", []))]
        ).casefold()
        if re.search(r"cookie|consent|privacy-banner|gdpr", marker):
            element.decompose()
    pieces: list[str] = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        item = _clean_text(element.get_text(" ", strip=True))
        if item and item not in pieces:
            pieces.append(item)
    text = _bounded_text(" ".join(pieces))
    return CrawledPage(url=url, title=title, description=description, text=text, facts=facts)


async def _fetch(
    client: Any,
    url: str,
    settings: Any,
    *,
    html_only: bool = True,
    max_bytes: int = MAX_PAGE_BYTES,
) -> _FetchedPage:
    current = normalize_url(url)
    user_agent = str(_setting(settings, "crawler_user_agent", "CompanyResearchAssistant/1.0"))[:200]
    for redirect_count in range(MAX_REDIRECTS + 1):
        # This validation is deliberately inside the loop, immediately before I/O.
        current = await validate_target_url(current)
        try:
            async with asyncio.timeout(PAGE_TIMEOUT_SECONDS):
                async with client.stream(
                    "GET",
                    current,
                    headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1"},
                    follow_redirects=False,
                    timeout=PAGE_TIMEOUT_SECONDS,
                ) as response:
                    status = int(response.status_code)
                    if status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count >= MAX_REDIRECTS:
                            raise CrawlError("redirect limit exceeded")
                        current = normalize_url(urljoin(current, location))
                        continue
                    if status >= 400:
                        raise CrawlError(f"HTTP status {status}")
                    content_type = str(response.headers.get("content-type", "")).split(";", 1)[0].strip().casefold()
                    if html_only and content_type and content_type not in {"text/html", "application/xhtml+xml"}:
                        raise CrawlError("non-HTML response")
                    raw_length = response.headers.get("content-length")
                    try:
                        if raw_length is not None and int(raw_length) > max_bytes:
                            raise CrawlError("response exceeds size limit")
                    except ValueError:
                        pass
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise CrawlError("response exceeds size limit")
                    return _FetchedPage(current, bytes(body), content_type)
        except asyncio.TimeoutError as exc:
            raise CrawlError("request timed out") from exc
    raise CrawlError("redirect limit exceeded")


async def _robots(client: Any, root_url: str, settings: Any) -> RobotFileParser | None:
    robots_url = normalize_url(urljoin(root_url, "/robots.txt"))
    try:
        fetched = await _fetch(client, robots_url, settings, html_only=False, max_bytes=MAX_ROBOTS_BYTES)
    except (UnsafeURLError, CrawlError, OSError):
        return None
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.parse(fetched.content.decode("utf-8", errors="replace").splitlines())
    except (UnicodeError, ValueError):
        return None
    return parser


async def _crawl_site(client: Any, root_url: str, settings: Any) -> CrawlResult:

    warnings: list[str] = []
    try:
        normalized_root = normalize_url(root_url)
        homepage = await _fetch(client, normalized_root, settings)
    except (UnsafeURLError, CrawlError, OSError) as exc:
        if isinstance(exc, UnsafeURLError):
            raise
        return CrawlResult(root_url=normalize_url(root_url), warnings=["Homepage could not be fetched."])

    final_root = homepage.url
    root_host = inspect_url(final_root).host
    robots = await _robots(client, final_root, settings)
    homepage_page = _extract_page(final_root, homepage.content)

    candidates: dict[str, tuple[int, str]] = {}
    homepage_soup = BeautifulSoup(homepage.content, "lxml")
    for anchor in homepage_soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href or urlsplit(href).scheme.casefold() in {"javascript", "mailto", "tel", "data"}:
            continue
        try:
            target = normalize_url(urljoin(final_root, href))
            parts = inspect_url(target)
        except (UnsafeURLError, ValueError):
            continue
        if parts.host != root_host or _skip_url(target, final_root):
            continue
        if robots is not None and not robots.can_fetch(str(_setting(settings, "crawler_user_agent", "*")), target):
            continue
        score = _link_score(target, anchor.get_text(" ", strip=True))
        if score <= 0:
            continue
        candidates[target] = max(candidates.get(target, (0, "")), (score, _clean_text(anchor.get_text(" ", strip=True))))
    selected = [url for url, _ in sorted(candidates.items(), key=lambda item: (-item[1][0], item[0]))[: MAX_PAGES - 1]]

    pages: list[CrawledPage] = [homepage_page]
    seen_hashes = {hashlib.sha256(homepage_page.text.encode("utf-8")).hexdigest()}
    semaphore = asyncio.Semaphore(3)

    async def fetch_child(target: str) -> CrawledPage | None:
        async with semaphore:
            try:
                fetched = await _fetch(client, target, settings)
                if not _same_host(fetched.url, final_root):
                    raise CrawlError("redirected off the crawl host")
                return _extract_page(fetched.url, fetched.content)
            except (UnsafeURLError, CrawlError, OSError):
                warnings.append("A linked page could not be fetched.")
                return None

    try:
        async with asyncio.timeout(AGGREGATE_TIMEOUT_SECONDS):
            children = await asyncio.gather(*(fetch_child(target) for target in selected))
    except asyncio.TimeoutError:
        warnings.append("Crawl time budget reached before all linked pages completed.")
        children = []
    for page in children:
        if page is None:
            continue
        digest = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        pages.append(page)

    facts: dict[str, Any] = {}
    for page in pages:
        for key, value in page.facts.items():
            if value and key not in facts:
                facts[key] = value
    text_parts: list[str] = []
    sources: list[dict[str, str]] = []
    total_chars = 0
    for page in pages:
        remaining = MAX_TOTAL_CHARS - total_chars
        if remaining <= 0:
            break
        section = _bounded_text(" ".join(item for item in (page.title, page.description, page.text) if item), remaining)
        if not section:
            continue
        text_parts.append(section)
        total_chars += len(section)
        sources.append({"title": page.title or page.url, "url": page.url, "source_type": "website"})
    if not sources:
        warnings.append("No meaningful static HTML evidence was found.")
    # Stable ordering and bounded warning output keep this object safe for API use.
    warnings = list(dict.fromkeys(warnings))[:10]
    return CrawlResult(
        root_url=final_root,
        company_facts=facts,
        page_text="\n\n".join(text_parts)[:MAX_TOTAL_CHARS],
        sources=sources[:15],
        warnings=warnings,
        pages=pages,
    )


async def crawl_site(client: Any, root_url: str, settings: Any) -> CrawlResult:
    """Run the crawler under its aggregate wall-clock budget."""

    normalized_root = normalize_url(root_url)
    try:
        async with asyncio.timeout(AGGREGATE_TIMEOUT_SECONDS):
            return await _crawl_site(client, normalized_root, settings)
    except asyncio.TimeoutError:
        return CrawlResult(
            root_url=normalized_root,
            warnings=["Crawl time budget reached before the site finished loading."],
        )
