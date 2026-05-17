"""
VECTOR PageSpeed Client — Core Web Vitals and performance analysis.

Calls Google PageSpeed Insights API to get LCP, CLS, FID, performance scores
and optimization opportunities. No gcloud needed — uses PSI API key or free tier.

Usage:
    client = PageSpeedClient()
    result = await client.analyze("https://example.com")
    print(result["scores"])  # {"performance": 82, "mobile": 74}
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from core.config import CONFIG

PSI_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def _load_api_key() -> str | None:
    """Read PAGESPEED_API_KEY from CONFIG or .env files."""
    key = CONFIG.get("api_keys", {}).get("pagespeed_api_key", "")
    if key:
        return key
    for env_file in [".env", ".env.local"]:
        try:
            with open(env_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("PAGESPEED_API_KEY=") and not line.startswith("#"):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            return val
        except OSError:
            pass
    return None


def _run_psi(url: str, strategy: str = "mobile", api_key: str | None = None) -> dict:
    params: dict[str, str] = {
        "url": url,
        "strategy": strategy,
        "category": "PERFORMANCE",
    }
    if api_key:
        params["key"] = api_key
    api_url = f"{PSI_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(api_url, headers={"User-Agent": "VECTOR/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"PSI API {e.code}: {body}")


def _extract_metrics(psi_data: dict) -> dict:
    """Extract Core Web Vitals and score from PSI response."""
    cats = psi_data.get("lighthouseResult", {}).get("categories", {})
    score = round((cats.get("performance", {}).get("score", 0) or 0) * 100)

    audits = psi_data.get("lighthouseResult", {}).get("audits", {})
    cwv = {}
    for metric_id in ("largest-contentful-paint", "cumulative-layout-shift",
                      "total-blocking-time", "speed-index", "interactive",
                      "first-contentful-paint"):
        a = audits.get(metric_id, {})
        cwv[metric_id] = {
            "displayValue": a.get("displayValue", ""),
            "score": a.get("score"),
            "numericValue": a.get("numericValue"),
        }

    # Opportunities (potential savings)
    opportunities = []
    for audit_id, audit in audits.items():
        if audit.get("details", {}).get("type") == "opportunity":
            savings_ms = audit.get("details", {}).get("overallSavingsMs", 0)
            if savings_ms and savings_ms > 200:
                opportunities.append({
                    "id": audit_id,
                    "title": audit.get("title", ""),
                    "savings_ms": round(savings_ms),
                    "description": audit.get("description", "")[:200],
                })
    opportunities.sort(key=lambda x: x["savings_ms"], reverse=True)

    return {
        "performance_score": score,
        "core_web_vitals": cwv,
        "opportunities": opportunities[:5],
    }


class PageSpeedClient:
    """
    VECTOR's PageSpeed Insights client.
    Analyzes mobile + desktop performance for any URL.
    """

    def __init__(self) -> None:
        self._api_key = _load_api_key()
        if not self._api_key:
            logger.debug("[VECTOR][pagespeed] no API key — using free tier (rate limited)")

    def analyze_url(self, url: str) -> dict:
        """Analyze a single URL on both mobile and desktop."""
        with ThreadPoolExecutor(max_workers=2) as pool:
            mob_fut = pool.submit(_run_psi, url, "mobile",  self._api_key)
            dsk_fut = pool.submit(_run_psi, url, "desktop", self._api_key)
            try:
                mobile  = _extract_metrics(mob_fut.result())
                desktop = _extract_metrics(dsk_fut.result())
            except Exception as e:
                logger.warning("[VECTOR][pagespeed] PSI failed for {}: {}", url, e)
                return {"url": url, "error": str(e)}

        logger.info(
            "[VECTOR][pagespeed] {} mobile={} desktop={}",
            url[:60], mobile["performance_score"], desktop["performance_score"],
        )
        return {
            "url": url,
            "scores": {
                "mobile":  mobile["performance_score"],
                "desktop": desktop["performance_score"],
            },
            "mobile":  mobile,
            "desktop": desktop,
        }

    def analyze_urls(self, urls: list[str], max_workers: int = 3) -> list[dict]:
        """Analyze multiple URLs concurrently."""
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {pool.submit(self.analyze_url, u): u for u in urls}
            for fut in futs:
                try:
                    results.append(fut.result(timeout=90))
                except Exception as e:
                    results.append({"url": futs[fut], "error": str(e)})
        return results

    async def analyze(self, url: str) -> dict:
        """Async wrapper for analyze_url."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.analyze_url, url)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    client = PageSpeedClient()
    print(f"OK pagespeed_client.py — PageSpeedClient ready (api_key={'set' if client._api_key else 'free tier'})")
