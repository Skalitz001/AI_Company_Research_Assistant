"""URL normalization and SSRF protection for outbound crawler requests.

The crawler calls :func:`validate_target_url` immediately before every request.  DNS
validation intentionally happens in a worker thread because ``getaddrinfo`` is a
blocking standard-library call.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class UnsafeURLError(ValueError):
    """Raised when a URL is malformed or does not pass outbound URL policy."""


# Hostnames used by cloud metadata services, in addition to the address checks.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google.com",
        "instance-data.ec2.internal",
        "metadata",
    }
)
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal")
_TRACKING_PARAMETERS = frozenset(
    {
        "gclid",
        "dclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_",
        "source",
    }
)


def _hostname(value: str) -> str:
    try:
        literal = ipaddress.ip_address(value)
    except ValueError:
        literal = None
    if literal is not None:
        return str(literal).lower()
    try:
        host = value.encode("idna").decode("ascii").rstrip(".").lower()
    except (UnicodeError, AttributeError) as exc:
        raise UnsafeURLError("Invalid hostname") from exc
    if not host or any(ord(char) < 32 or char.isspace() for char in host):
        raise UnsafeURLError("Invalid hostname")
    return host


def _split_and_check(url: str, *, add_https: bool = False):
    if not isinstance(url, str):
        raise UnsafeURLError("URL must be a string")
    value = url.strip()
    if not value or any(ord(char) < 32 for char in value):
        raise UnsafeURLError("URL contains control characters")
    if add_https and "://" not in value:
        value = f"https://{value}"
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURLError("Malformed URL") from exc
    if scheme not in {"http", "https"}:
        raise UnsafeURLError("Only HTTP and HTTPS URLs are allowed")
    if not host:
        raise UnsafeURLError("URL has no hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURLError("URLs with credentials are not allowed")
    default_port = 80 if scheme == "http" else 443
    if port is not None and port != default_port:
        raise UnsafeURLError("Only default HTTP(S) ports are allowed")
    host = _hostname(host)
    if host in _BLOCKED_HOSTNAMES or any(host.endswith(suffix) for suffix in _BLOCKED_SUFFIXES):
        raise UnsafeURLError("Local and metadata hostnames are not allowed")
    return parsed, scheme, host, default_port


def _unsafe_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    # These properties cover both IPv4 and IPv6, including IPv4-mapped IPv6.
    return bool(
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_global is False
    )


def _literal_address(host: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(host), (ipaddress.IPv4Address, ipaddress.IPv6Address))
    except ValueError:
        return False


async def resolve_hostname(host: str, port: int) -> list[str]:
    """Resolve a host off the event loop; kept separate so tests can monkeypatch it."""

    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except (OSError, socket.gaierror) as exc:
        raise UnsafeURLError("Hostname could not be resolved") from exc
    addresses: list[str] = []
    for record in records:
        sockaddr = record[4]
        if sockaddr:
            address = str(sockaddr[0])
            if address not in addresses:
                addresses.append(address)
    if not addresses:
        raise UnsafeURLError("Hostname could not be resolved")
    return addresses


async def validate_target_url(url: str) -> str:
    """Validate a URL and its DNS answers, returning its normalized URL.

    This is asynchronous by design: all hostname DNS resolution goes through
    ``asyncio.to_thread`` and must complete before a request is made.
    """

    normalized = normalize_url(url)
    parsed, _scheme, host, port = _split_and_check(normalized)
    if _literal_address(host):
        addresses = [host]
    else:
        addresses = await resolve_hostname(host, port)
    if any(_unsafe_address(address) for address in addresses):
        raise UnsafeURLError("URL resolves to a disallowed network address")
    return normalized


def normalize_url(url: str) -> str:
    """Canonicalize an HTTP(S) URL without performing DNS resolution."""

    parsed, scheme, host, default_port = _split_and_check(url, add_https=True)
    # urlsplit accepts a bare value with a path; reject likely malformed domain
    # inputs instead of treating them as a hostname accidentally.
    if not host or "." not in host and not _literal_address(host):
        raise UnsafeURLError("URL hostname is not a valid domain")
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if parsed.port is not None and parsed.port != default_port:
        raise UnsafeURLError("Only default HTTP(S) ports are allowed")
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    # Empty and slash-only paths are one canonical homepage URL.  Preserve a
    # meaningful trailing slash only for the root, eliminating slash duplicates.
    if len(path) > 1:
        path = path.rstrip("/")
    pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in _TRACKING_PARAMETERS:
            continue
        pairs.append((key, value))
    query = urlencode(sorted(pairs), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


@dataclass(frozen=True)
class URLParts:
    """Small public value object useful to callers that need host comparison."""

    url: str
    scheme: str
    host: str
    port: int


def inspect_url(url: str) -> URLParts:
    """Parse and syntactically validate a URL without resolving DNS."""

    normalized = normalize_url(url)
    _parsed, scheme, host, port = _split_and_check(normalized)
    return URLParts(normalized, scheme, host, port)
