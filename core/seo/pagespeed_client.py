"""
VECTOR PageSpeed Client — Core Web Vitals and performance analysis.

Calls Google PageSpeed Insights API to get LCP, CLS, FID, performance scores
and optimization opportunities. No gcloud needed — uses PSI API key or free tier.

Usage:
    client = PageSpeedClient()
    result = await client.analyze("https://example.com")
    logger.info(result["scores"])  # {"performance": 82, "mobile": 74}

"""
from __future__ import annotations

__all__ = [
    "PageSpeedClient",
    "PSI_API",
]


import asyncio
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

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
        except OSError as e:
            logger.debug("[VECTOR][pagespeed] couldn't read {}: {}", env_file, e)
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


def _score_indicator(score: int | None) -> str:
    """Map Lighthouse 0-100 score to a human label. Ported from show_pagespeed.py."""
    if score is None:
        return "N/A"
    if score >= 90:
        return "Good"
    if score >= 50:
        return "Needs Work"
    return "Poor"


def _extract_crux(psi_data: dict) -> dict:
    """
    Extract CrUX (Chrome User Experience Report) data from PSI response.
    Ported from show_pagespeed.py — parses the loadingExperience key.

    CrUX = real user measurements from actual Chrome users in the field.
    This is DIFFERENT from Lighthouse synthetic scores (which run in a lab).
    CrUX data is more reliable for diagnosing what real users actually experience.

    Returns dict with lcp, fid, cls, fcp ratings (FAST/AVERAGE/SLOW) + percentiles.
    Returns empty dict if CrUX data is unavailable (no field data for this URL).
    """
    exp = psi_data.get("loadingExperience", {})
    if not exp:
        return {"available": False, "reason": "no_field_data"}

    overall = exp.get("overall_category", "unknown")
    metrics_raw = exp.get("metrics", {})
    crux: dict = {"available": True, "overall": overall}

    METRIC_MAP = [
        ("LARGEST_CONTENTFUL_PAINT_MS",    "lcp",  "ms"),
        ("FIRST_INPUT_DELAY_MS",           "fid",  "ms"),
        ("CUMULATIVE_LAYOUT_SHIFT_SCORE",  "cls",  "score"),
        ("FIRST_CONTENTFUL_PAINT_MS",      "fcp",  "ms"),
        ("INTERACTION_TO_NEXT_PAINT",      "inp",  "ms"),
        ("EXPERIMENTAL_TIME_TO_FIRST_BYTE","ttfb", "ms"),
    ]
    for api_key, label, unit in METRIC_MAP:
        m = metrics_raw.get(api_key, {})
        if not m:
            continue
        crux[label] = {
            "rating":     m.get("category", "unknown"),   # FAST / AVERAGE / SLOW
            "percentile": m.get("percentile"),             # e.g. 2400 (ms at 75th pct)
            "unit":       unit,
        }
        # Distribution histogram (Good/Needs Improvement/Poor proportions)
        dist = m.get("distributions", [])
        if dist:
            crux[label]["distribution"] = {
                "good":          round((dist[0].get("proportion", 0) if len(dist) > 0 else 0) * 100, 1),
                "needs_improve": round((dist[1].get("proportion", 0) if len(dist) > 1 else 0) * 100, 1),
                "poor":          round((dist[2].get("proportion", 0) if len(dist) > 2 else 0) * 100, 1),
            }

    return crux


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
        """
        Analyze a single URL on both mobile and desktop.
        Returns Lighthouse synthetic scores + CrUX real-user data.
        """
        with ThreadPoolExecutor(max_workers=2) as pool:
            mob_fut = pool.submit(_run_psi, url, "mobile",  self._api_key)
            dsk_fut = pool.submit(_run_psi, url, "desktop", self._api_key)
            try:
                mob_raw = mob_fut.result()
                dsk_raw = dsk_fut.result()
                mobile  = _extract_metrics(mob_raw)
                desktop = _extract_metrics(dsk_raw)
                # CrUX comes from mobile response (mobile is the primary signal for Google)
                crux = _extract_crux(mob_raw)
            except Exception as e:
                logger.warning("[VECTOR][pagespeed] PSI failed for {}: {}", url, e)
                return {"url": url, "error": str(e)}

        mobile_label  = _score_indicator(mobile["performance_score"])
        desktop_label = _score_indicator(desktop["performance_score"])
        crux_label    = crux.get("overall", "unknown")

        logger.info(
            "[VECTOR][pagespeed] {} mobile={} ({}) desktop={} ({}) crux={}",
            url[:60], mobile["performance_score"], mobile_label,
            desktop["performance_score"], desktop_label, crux_label,
        )
        return {
            "url": url,
            "scores": {
                "mobile":       mobile["performance_score"],
                "mobile_label": mobile_label,
                "desktop":      desktop["performance_score"],
                "desktop_label":desktop_label,
            },
            "mobile":  mobile,
            "desktop": desktop,
            "crux":    crux,   # real user data: lcp/fid/cls/fcp FAST/AVERAGE/SLOW ratings
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
