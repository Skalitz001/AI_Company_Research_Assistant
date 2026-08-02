import pytest

import backend.app.security.url as url_policy
from backend.app.security.url import UnsafeURLError, normalize_url, validate_target_url


def test_normalize_url_removes_tracking_and_fragment():
    assert normalize_url("https://Example.com/path/?utm_source=ad&b=2#section") == (
        "https://example.com/path?b=2"
    )


@pytest.mark.asyncio
async def test_literal_private_address_is_rejected_before_network_call():
    with pytest.raises(UnsafeURLError):
        await validate_target_url("http://127.0.0.1/internal")


@pytest.mark.asyncio
async def test_dns_answers_are_all_checked(monkeypatch):
    async def fake_resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34", "10.0.0.8"]

    monkeypatch.setattr(url_policy, "resolve_hostname", fake_resolve)
    with pytest.raises(UnsafeURLError):
        await validate_target_url("https://example.com")


@pytest.mark.parametrize(
    "value",
    [
        "ftp://example.com",
        "https://user:pass@example.com",
        "https://example.com:8443",
        "http://localhost",
    ],
)
def test_unsafe_url_syntax_is_rejected(value):
    with pytest.raises(UnsafeURLError):
        normalize_url(value)
