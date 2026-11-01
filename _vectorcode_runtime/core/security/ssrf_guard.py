"""
VECTOR SSRF Guard — blocks Server-Side Request Forgery attacks.

Prevents agents from making requests to:
  - Private IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x)
  - Link-local addresses (169.254.x — AWS/GCP metadata endpoints)
  - IPv6 loopback and link-local
  - Cloud metadata services (169.254.169.254, metadata.google.internal)
  - Internal VECTOR services

Call check_url() before ANY outbound HTTP request from agent tools.

Ported from the agent OS runtime web_fetch.rs SSRF protection layer.
"""
from __future__ import annotations

__all__ = [
    "get_ssrf_guard",
    "is_safe_url",
    "SSRFCheckResult",
    "SSRFGuard",
]


import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from loguru import logger


@dataclass
class SSRFCheckResult:
    safe: bool
    url: str
    reason: str = ""
    addresses: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.safe

    def __str__(self) -> str:
        return f"SAFE: {self.url}" if self.safe else f"BLOCKED: {self.url} ({self.reason})"


# â”€â”€ Blocked patterns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),    # carrier-grade NAT
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]

_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "metadata.google.internal",
    "metadata.aws.com",
    "169.254.169.254",              # AWS/Azure/GCP instance metadata
    "metadata.internal",
    "computeMetadata",
})

_BLOCKED_HOSTNAME_PATTERNS = re.compile(
    r"(?:169\.254\.169\.254|metadata\.google\.internal|"
    r"metadata\.aws\.com|\.local$|\.internal$)",
    re.IGNORECASE,
)

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_BLOCKED_PORTS = frozenset({22, 23, 25, 110, 143, 3306, 5432, 6379, 27017})  # SSH, SMTP, DB ports


class SSRFGuard:
    """
    URL safety checker — blocks SSRF attacks before HTTP requests.

    Usage:
        guard = SSRFGuard()
        result = guard.check_url("https://api.github.com/repos")
        if not result:
            raise SecurityError(result.reason)

        result = guard.check_url("http://169.254.169.254/latest/meta-data/")
        assert not result.safe  # blocked
    """

    def __init__(
        self,
        allow_private: bool = False,   # set True only for local dev with known-safe URLs
        resolve_dns: bool = False,     # resolve hostnames to check IPs (slower but safer)
    ) -> None:
        self._allow_private = allow_private
        self._resolve_dns = resolve_dns

    def check_url(self, url: str) -> SSRFCheckResult:
        """
        Check if a URL is safe to fetch.

        Checks:
          1. Valid URL structure
          2. Allowed scheme (http/https only)
          3. No blocked hostname
          4. No private IP in hostname
          5. No blocked port
          6. Optional DNS resolution check
        """
        if not url or not url.strip():
            return SSRFCheckResult(safe=False, url=url, reason="Empty URL")

        try:
            parsed = urlparse(url.strip())
        except Exception as e:
            return SSRFCheckResult(safe=False, url=url, reason=f"Invalid URL: {e}")

        # 1. Scheme check
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return SSRFCheckResult(
                safe=False, url=url,
                reason=f"Scheme '{parsed.scheme}' not allowed (only http/https)"
            )

        host = parsed.hostname or ""
        if not host:
            return SSRFCheckResult(safe=False, url=url, reason="No hostname")

        # 2. Blocked hostname
        # allow_private=True permits "localhost" so configured local services (Ollama) work.
        # Other entries in _BLOCKED_HOSTNAMES (cloud metadata) are always blocked.
        if host.lower() in _BLOCKED_HOSTNAMES:
            if not (self._allow_private and host.lower() == "localhost"):
                logger.warning("[VECTOR][ssrf] blocked hostname: {}", host)
                return SSRFCheckResult(safe=False, url=url, reason=f"Blocked hostname: {host}")

        if _BLOCKED_HOSTNAME_PATTERNS.search(host):
            return SSRFCheckResult(safe=False, url=url, reason=f"Blocked hostname pattern: {host}")

        resolved_addresses: list[str] = []

        # 3. Non-public IP check (direct IP in URL). is_global also rejects unspecified, reserved, multicast, documentation,
        # link-local, loopback and IPv4-mapped private addresses, not just a hand-maintained list of private ranges.
        if not self._allow_private:
            try:
                ip = ipaddress.ip_address(host)
                if not ip.is_global:
                    logger.warning("[VECTOR][ssrf] blocked non-public IP: {}", host)
                    return SSRFCheckResult(safe=False, url=url, reason=f"Private/reserved IP address: {host}")
                resolved_addresses.append(str(ip))
            except ValueError:
                pass  # hostname, not IP — continue

        # 4. Port check
        port = parsed.port
        if port and port in _BLOCKED_PORTS:
            return SSRFCheckResult(safe=False, url=url, reason=f"Blocked port: {port}")

        # 5. DNS resolution check (optional, slower)
        if self._resolve_dns and not self._allow_private:
            try:
                resolved = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
                for _, _, _, _, addr in resolved:
                    ip_str = addr[0]
                    try:
                        ip = ipaddress.ip_address(ip_str)
                        if not ip.is_global:
                            logger.warning("[VECTOR][ssrf] blocked DNS-resolved IP: {} → {}", host, ip_str)
                            return SSRFCheckResult(safe=False, url=url, reason=f"DNS resolves to private/reserved IP: {ip_str}")
                        normalised = str(ip)
                        if normalised not in resolved_addresses:
                            resolved_addresses.append(normalised)
                    except ValueError:
                        return SSRFCheckResult(safe=False, url=url, reason=f"DNS returned an invalid address: {ip_str}")
                if not resolved_addresses:
                    return SSRFCheckResult(safe=False, url=url, reason="DNS returned no usable addresses")
            except OSError as exc:
                # Fail closed: otherwise the HTTP client would perform an unconstrained second lookup.
                return SSRFCheckResult(safe=False, url=url, reason=f"DNS resolution failed: {exc}")

        return SSRFCheckResult(safe=True, url=url, addresses=tuple(resolved_addresses))

    def filter_urls(self, urls: list[str]) -> tuple[list[str], list[SSRFCheckResult]]:
        """Return (safe_urls, blocked_results)."""
        safe, blocked = [], []
        for url in urls:
            result = self.check_url(url)
            if result.safe:
                safe.append(url)
            else:
                blocked.append(result)
        return safe, blocked


_guard: SSRFGuard | None = None


def get_ssrf_guard() -> SSRFGuard:
    global _guard
    if _guard is None:
        _guard = SSRFGuard()
    return _guard


def is_safe_url(url: str) -> bool:
    return get_ssrf_guard().check_url(url).safe


if __name__ == "__main__":
    guard = SSRFGuard()

    # Safe URLs
    assert guard.check_url("https://api.github.com/repos").safe
    assert guard.check_url("https://arxiv.org/abs/1234.56789").safe
    assert guard.check_url("https://duckduckgo.com/html/?q=python").safe

    # SSRF attacks
    assert not guard.check_url("http://169.254.169.254/latest/meta-data/").safe
    assert not guard.check_url("http://localhost:8080/admin").safe  # blocked without allow_private
    assert not guard.check_url("http://127.0.0.1:6379/").safe
    # allow_private=True lets localhost through (for Ollama and other local services)
    assert SSRFGuard(allow_private=True).check_url("http://localhost:11434/api/chat").safe
    assert not guard.check_url("http://10.0.0.1/internal").safe
    assert not guard.check_url("http://192.168.1.1/router").safe
    assert not guard.check_url("ftp://files.example.com/data").safe
    assert not guard.check_url("http://metadata.google.internal").safe
    assert not guard.check_url("http://example.local/admin").safe

    # Edge cases
    assert not guard.check_url("").safe
    assert not guard.check_url("not-a-url").safe

    # Filter batch
    urls = ["https://github.com", "http://localhost/bad", "https://arxiv.org"]
    safe, blocked = guard.filter_urls(urls)
    assert len(safe) == 2 and len(blocked) == 1

    print("OK ssrf_guard.py — private IPs, metadata endpoints, scheme check all blocked")
