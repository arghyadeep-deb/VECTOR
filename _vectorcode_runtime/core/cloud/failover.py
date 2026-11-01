"""FailoverManager — round-robin endpoint failover for cloud brain servers."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


@dataclass
class _Endpoint:
    url: str
    region: str
    healthy: bool = True
    last_check: float = field(default_factory=time.time)
    failures: int = 0


class FailoverManager:
    """Round-robin failover across multiple cloud brain endpoints.

    Usage:
        fm = FailoverManager()
        fm.register_endpoint("https://brain1.fly.dev", "us-east")
        fm.register_endpoint("https://brain2.fly.dev", "eu-west")
        url = fm.current_endpoint()   # returns first healthy URL
    """

    def __init__(self, timeout_sec: float = 5.0) -> None:
        self._endpoints: list[_Endpoint] = []
        self._index = 0
        self._timeout = timeout_sec

    def register_endpoint(self, url: str, region: str = "default") -> None:
        url = url.rstrip("/")
        if any(e.url == url for e in self._endpoints):
            return
        self._endpoints.append(_Endpoint(url=url, region=region))
        logger.info("[VECTOR][failover] registered endpoint {} ({})", url, region)

    def current_endpoint(self) -> Optional[str]:
        """Return the current healthy endpoint URL, or None if all are down."""
        healthy = [e for e in self._endpoints if e.healthy]
        if not healthy:
            return None
        ep = healthy[self._index % len(healthy)]
        return ep.url

    def mark_unhealthy(self, url: str) -> None:
        for ep in self._endpoints:
            if ep.url == url:
                ep.healthy = False
                ep.failures += 1
                logger.warning("[VECTOR][failover] {} marked unhealthy (failures={})", url, ep.failures)
                self._index = (self._index + 1) % max(len(self._endpoints), 1)
                return

    def mark_healthy(self, url: str) -> None:
        for ep in self._endpoints:
            if ep.url == url:
                ep.healthy = True
                ep.failures = 0
                logger.info("[VECTOR][failover] {} recovered", url)
                return

    async def health_check_all(self) -> dict[str, bool]:
        """Async health check every registered endpoint at /health."""
        if not _HTTPX_OK:
            logger.warning("[VECTOR][failover] httpx not installed — health checks skipped")
            return {}

        results: dict[str, bool] = {}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for ep in self._endpoints:
                try:
                    resp = await client.get(f"{ep.url}/health")
                    ok = resp.status_code < 400
                except Exception:
                    ok = False
                ep.healthy = ok
                ep.last_check = time.time()
                results[ep.url] = ok
                logger.debug("[VECTOR][failover] health {} → {}", ep.url, "OK" if ok else "FAIL")
        return results

    def status(self) -> list[dict]:
        return [
            {
                "url": e.url,
                "region": e.region,
                "healthy": e.healthy,
                "failures": e.failures,
                "last_check": e.last_check,
            }
            for e in self._endpoints
        ]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    fm = FailoverManager()
    fm.register_endpoint("https://brain1.fly.dev", "us-east")
    fm.register_endpoint("https://brain2.fly.dev", "eu-west")
    assert fm.current_endpoint() == "https://brain1.fly.dev"
    fm.mark_unhealthy("https://brain1.fly.dev")
    assert fm.current_endpoint() == "https://brain2.fly.dev"
    fm.mark_healthy("https://brain1.fly.dev")
    assert len(fm.status()) == 2
    print("OK failover.py")
