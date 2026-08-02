import httpx
import pytest

from backend.app.config import Settings
from backend.app.services import crawler


HOME = b"""
<html><head><title>Acme Home</title><meta name='description' content='Acme builds useful tools.'>
<script type='application/ld+json'>{"@type":"Organization","name":"Acme Corp","telephone":"+1 555 0100","address":{"streetAddress":"1 Main St","addressCountry":"US"}}</script>
</head><body>
<nav>Navigation login</nav><h1>Acme Corp</h1><p>We build useful tools for teams.</p>
<a href='/about'>About</a><a href='/contact'>Contact</a><a href='/login'>Login</a>
</body></html>
"""
ABOUT = b"<html><head><title>About Acme</title></head><body><h1>About</h1><p>Our services help teams work better.</p></body></html>"
CONTACT = b"<html><head><title>Contact Acme</title></head><body><h1>Contact</h1><a href='tel:+1-555-0100'>Call</a><p>Contact our team.</p></body></html>"


@pytest.mark.asyncio
async def test_crawl_extracts_fact_text_and_scored_pages(monkeypatch):
    async def bypass_dns(value: str) -> str:
        return crawler.normalize_url(value)

    monkeypatch.setattr(crawler, "validate_target_url", bypass_dns)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if request.url.path == "/about":
            return httpx.Response(200, content=ABOUT, headers={"content-type": "text/html"})
        if request.url.path == "/contact":
            return httpx.Response(200, content=CONTACT, headers={"content-type": "text/html"})
        if request.url.path == "/login":
            return httpx.Response(200, content=b"<html>login</html>", headers={"content-type": "text/html"})
        return httpx.Response(200, content=HOME, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        result = await crawler.crawl_site(client, "https://acme.example", Settings())

    assert len(result.pages) <= crawler.MAX_PAGES
    assert "Acme Corp" in result.page_text
    assert "Acme builds useful tools." in result.page_text
    assert result.company_facts["phone"] == "+1 555 0100"
    assert result.company_facts["address"] == "1 Main St, US"
    assert {page.url for page in result.pages} == {
        "https://acme.example/",
        "https://acme.example/about",
        "https://acme.example/contact",
    }
    assert all("login" not in page.url for page in result.pages)
