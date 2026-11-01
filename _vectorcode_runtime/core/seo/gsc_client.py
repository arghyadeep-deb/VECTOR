"""
VECTOR GSC Client — Google Search Console data fetcher and analyzer.

Fetches real search performance data: clicks, impressions, CTR, position
per page and query. Outputs structured JSON for SEO analysis.

Requires:
  - gcloud CLI installed + authenticated (gcloud auth application-default login)
  - GSC site verified in Google Search Console
  - GOOGLE_CREDENTIALS_PATH set in CONFIG (or gcloud ADC)

Usage:
    client = GSCClient()
    data = await client.fetch("sc-domain:example.com", days=28)
    analysis = client.analyze(data)
"""
from __future__ import annotations

__all__ = [
    "GSCClient",
    "list_sites",
    "PAGE_GROUPS",
    "URLInspector",
]


import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from loguru import logger


# ── Page group patterns (maps URL path patterns to category labels) ────────────

PAGE_GROUPS = [
    ("blog",         r"/blog/"),
    ("products",     r"/product"),
    ("locations",    r"/location"),
    ("services",     r"/service"),
    ("pricing",      r"/pricing"),
    ("docs",         r"/docs?/"),
    ("about",        r"/about"),
    ("faq",          r"/faq"),
    ("landing",      r"/lp/"),
    ("case-studies", r"/case-studi"),
]


# ── gcloud helpers ─────────────────────────────────────────────────────────────

def _gcloud_cmd(args: list[str]) -> list[str]:
    """Build a portable gcloud subprocess command (handles Windows .cmd)."""
    import shutil
    if not args or args[0] != "gcloud":
        raise ValueError("args must start with 'gcloud'")
    gcloud = shutil.which("gcloud")
    if sys.platform == "win32" and gcloud and gcloud.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", gcloud, *args[1:]]
    return [gcloud or "gcloud", *args[1:]]


def _gcloud_run(args: list[str], **kwargs):
    return subprocess.run(_gcloud_cmd(args), **kwargs)


def _get_quota_project() -> str | None:
    adc_dir = os.environ.get("CLOUDSDK_CONFIG") or os.path.join(
        os.path.expanduser("~"), ".config", "gcloud"
    )
    adc_path = os.path.join(adc_dir, "application_default_credentials.json")
    try:
        with open(adc_path) as f:
            data = json.load(f)
        return data.get("quota_project_id") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _get_access_token() -> str | None:
    try:
        result = _gcloud_run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, timeout=15,
        )
        token = result.stdout.strip()
        return token if token and "Error" not in token else None
    except Exception:
        return None


# ── GSC API calls ──────────────────────────────────────────────────────────────

def _gsc_request(
    endpoint: str,
    payload: dict | None = None,
    method: str = "POST",
    access_token: str | None = None,
) -> dict:
    token = access_token or _get_access_token()
    if not token:
        raise RuntimeError(
            "No gcloud access token. Run: gcloud auth application-default login"
        )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    quota = _get_quota_project()
    if quota:
        headers["x-goog-user-project"] = quota

    base = "https://searchconsole.googleapis.com/webmasters/v3"
    url = f"{base}/{endpoint}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"GSC API {e.code}: {body}")


def list_sites(access_token: str | None = None) -> list[str]:
    """List all verified sites in Google Search Console."""
    data = _gsc_request("sites", method="GET", access_token=access_token)
    return [s["siteUrl"] for s in data.get("siteEntry", [])]


def _query_performance(
    site: str,
    start_date: str,
    end_date: str,
    dimensions: list[str],
    row_limit: int = 25000,
    access_token: str | None = None,
) -> list[dict]:
    encoded_site = urllib.parse.quote(site, safe="")
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
    }
    data = _gsc_request(
        f"sites/{encoded_site}/searchAnalytics/query",
        payload=payload,
        access_token=access_token,
    )
    return data.get("rows", [])


# ── Analysis helpers ───────────────────────────────────────────────────────────

def _position_buckets(query_rows: list[dict]) -> dict:
    """
    Group queries by average rank position into 4 bands.
    Ported from show_gsc.py — surfaces at a glance where the easy wins are.

    Bands:
      1-3   : Top 3 (already winning — protect these)
      4-10  : Page 1 lower (push to top 3 — biggest ROI)
      11-20 : Page 2 near-miss (easy wins with content/link updates)
      21+   : Buried (major work needed)
    """
    bands: dict[str, list[dict]] = {"1-3": [], "4-10": [], "11-20": [], "21+": []}

    for row in query_rows:
        # Aggregate by query first
        pass

    # Build per-query aggregates
    queries: dict[str, dict] = {}
    for row in query_rows:
        q = row["keys"][0] if row.get("keys") else ""
        if q not in queries:
            queries[q] = {"query": q, "clicks": 0, "impressions": 0,
                          "position_sum": 0, "imp_sum": 0}
        queries[q]["clicks"] += row.get("clicks", 0)
        queries[q]["impressions"] += row.get("impressions", 0)
        imp = row.get("impressions", 1) or 1
        queries[q]["position_sum"] += row.get("position", 0) * imp
        queries[q]["imp_sum"] += imp

    for q_data in queries.values():
        avg_pos = q_data["position_sum"] / max(q_data["imp_sum"], 1)
        entry = {
            "query": q_data["query"],
            "clicks": q_data["clicks"],
            "impressions": q_data["impressions"],
            "position": round(avg_pos, 1),
        }
        if avg_pos <= 3:
            bands["1-3"].append(entry)
        elif avg_pos <= 10:
            bands["4-10"].append(entry)
        elif avg_pos <= 20:
            bands["11-20"].append(entry)
        else:
            bands["21+"].append(entry)

    # Sort each band by impressions descending, keep top 10
    for band in bands:
        bands[band].sort(key=lambda x: x["impressions"], reverse=True)

    return {
        "counts": {band: len(entries) for band, entries in bands.items()},
        "top_queries": {band: entries[:10] for band, entries in bands.items()},
        "insight": _bucket_insight(
            {band: len(entries) for band, entries in bands.items()}
        ),
    }


def _bucket_insight(counts: dict[str, int]) -> str:
    """Generate a one-line insight from position bucket counts."""
    total = sum(counts.values()) or 1
    page2_pct = round(counts.get("11-20", 0) / total * 100)
    buried_pct = round(counts.get("21+", 0) / total * 100)
    top3_pct   = round(counts.get("1-3", 0) / total * 100)

    if buried_pct > 60:
        return f"{buried_pct}% of keywords buried (pos 21+) — major content and authority gaps"
    if page2_pct > 40:
        return f"{page2_pct}% on page 2 — high potential for quick wins with content updates"
    if top3_pct > 50:
        return f"{top3_pct}% ranking top 3 — strong position, focus on defending and expanding"
    return f"Mixed: {counts.get('1-3',0)} top-3, {counts.get('4-10',0)} page-1, {counts.get('11-20',0)} page-2, {counts.get('21+',0)} buried"


def _classify_page(url: str) -> str:
    for group, pattern in PAGE_GROUPS:
        if re.search(pattern, url, re.IGNORECASE):
            return group
    return "other"


def _top_pages(rows: list[dict], n: int = 20) -> list[dict]:
    pages: dict[str, dict] = {}
    for row in rows:
        url = row["keys"][0] if row.get("keys") else ""
        if url not in pages:
            pages[url] = {"url": url, "clicks": 0, "impressions": 0, "position_sum": 0, "count": 0}
        pages[url]["clicks"] += row.get("clicks", 0)
        pages[url]["impressions"] += row.get("impressions", 0)
        pages[url]["position_sum"] += row.get("position", 0) * row.get("impressions", 1)
        pages[url]["count"] += 1

    result = []
    for p in pages.values():
        imp = p["impressions"] or 1
        p["position"] = round(p["position_sum"] / imp, 1)
        p["ctr"] = round(p["clicks"] / imp * 100, 2)
        p["group"] = _classify_page(p["url"])
        del p["position_sum"], p["count"]
        result.append(p)

    return sorted(result, key=lambda x: x["clicks"], reverse=True)[:n]


def _top_queries(rows: list[dict], n: int = 30) -> list[dict]:
    queries: dict[str, dict] = {}
    for row in rows:
        q = row["keys"][0] if row.get("keys") else ""
        if q not in queries:
            queries[q] = {"query": q, "clicks": 0, "impressions": 0, "position_sum": 0, "count": 0}
        queries[q]["clicks"] += row.get("clicks", 0)
        queries[q]["impressions"] += row.get("impressions", 0)
        queries[q]["position_sum"] += row.get("position", 0) * row.get("impressions", 1)
        queries[q]["count"] += 1

    result = []
    for q in queries.values():
        imp = q["impressions"] or 1
        q["position"] = round(q["position_sum"] / imp, 1)
        q["ctr"] = round(q["clicks"] / imp * 100, 2)
        del q["position_sum"], q["count"]
        result.append(q)

    return sorted(result, key=lambda x: x["clicks"], reverse=True)[:n]


def _opportunities(pages: list[dict]) -> list[dict]:
    """Identify quick-win opportunities: high impressions, low clicks (CTR < 3%, position 4-20)."""
    opps = []
    for p in pages:
        if p["impressions"] >= 500 and p["ctr"] < 3.0 and 4 <= p["position"] <= 20:
            opps.append({
                "url": p["url"],
                "impressions": p["impressions"],
                "ctr": p["ctr"],
                "position": p["position"],
                "potential_clicks": round(p["impressions"] * 0.08),  # ~8% CTR at pos 3-4
                "opportunity": "improve_ctr",
            })
    return sorted(opps, key=lambda x: x["potential_clicks"], reverse=True)[:10]


# ── GSCClient ─────────────────────────────────────────────────────────────────

class GSCClient:
    """
    VECTOR's Google Search Console client.
    Fetches real traffic data and surfaces SEO opportunities.
    """

    def __init__(self) -> None:
        self._token: str | None = None

    def _ensure_token(self) -> str:
        if not self._token:
            self._token = _get_access_token()
        if not self._token:
            raise RuntimeError(
                "[VECTOR][gsc] No access token. Run: gcloud auth application-default login"
            )
        return self._token

    def list_sites(self) -> list[str]:
        """List all GSC-verified sites for this account."""
        token = self._ensure_token()
        sites = list_sites(access_token=token)
        logger.info("[VECTOR][gsc] found {} verified sites", len(sites))
        return sites

    def fetch(
        self,
        site: str,
        days: int = 28,
        row_limit: int = 25000,
    ) -> dict:
        """
        Fetch search analytics for a site over the past N days.
        Returns raw rows for pages and queries.
        """
        token = self._ensure_token()
        end = date.today() - timedelta(days=3)  # GSC has 3-day lag
        start = end - timedelta(days=days)
        s_str = start.strftime("%Y-%m-%d")
        e_str = end.strftime("%Y-%m-%d")

        logger.info("[VECTOR][gsc] fetching {} ({} days: {} → {})", site, days, s_str, e_str)

        with ThreadPoolExecutor(max_workers=2) as pool:
            page_fut  = pool.submit(_query_performance, site, s_str, e_str, ["page"],  row_limit, token)
            query_fut = pool.submit(_query_performance, site, s_str, e_str, ["query"], row_limit, token)
            page_rows  = page_fut.result()
            query_rows = query_fut.result()

        logger.info("[VECTOR][gsc] {} page rows, {} query rows", len(page_rows), len(query_rows))
        return {
            "site": site,
            "period": {"start": s_str, "end": e_str, "days": days},
            "page_rows": page_rows,
            "query_rows": query_rows,
        }

    def analyze(self, data: dict) -> dict:
        """Analyze raw GSC data — returns top pages, queries, and opportunities."""
        page_rows  = data.get("page_rows", [])
        query_rows = data.get("query_rows", [])

        top_pages     = _top_pages(page_rows)
        top_queries   = _top_queries(query_rows)
        opportunities = _opportunities(top_pages)
        pos_buckets   = _position_buckets(query_rows)

        total_clicks = sum(r.get("clicks", 0) for r in page_rows)
        total_imps   = sum(r.get("impressions", 0) for r in page_rows)
        avg_ctr   = round(total_clicks / total_imps * 100, 2) if total_imps else 0
        avg_pos   = round(
            sum(r.get("position", 0) * r.get("impressions", 1) for r in page_rows)
            / max(total_imps, 1), 1
        )

        return {
            "site": data.get("site"),
            "period": data.get("period"),
            "summary": {
                "total_clicks": total_clicks,
                "total_impressions": total_imps,
                "avg_ctr_pct": avg_ctr,
                "avg_position": avg_pos,
                "total_pages": len(top_pages),
            },
            "top_pages":       top_pages,
            "top_queries":     top_queries,
            "opportunities":   opportunities,
            "position_buckets": pos_buckets,   # query ranking distribution (1-3, 4-10, 11-20, 21+)
        }

    async def fetch_and_analyze(self, site: str, days: int = 28) -> dict:
        """Async convenience: fetch + analyze in one call."""
        loop = asyncio.get_event_loop()
        raw  = await loop.run_in_executor(None, self.fetch, site, days)
        return self.analyze(raw)


# ── URL Inspection API ────────────────────────────────────────────────────────

def _inspect_url(
    site: str,
    url: str,
    access_token: str | None = None,
) -> dict:
    """
    Run URL Inspection API on a single URL.
    Returns indexing status, mobile usability, rich results, last crawl time.
    Requires broader OAuth scope: https://www.googleapis.com/auth/webmasters
    """
    token = access_token or _get_access_token()
    if not token:
        raise RuntimeError("No gcloud access token")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    quota = _get_quota_project()
    if quota:
        headers["x-goog-user-project"] = quota

    encoded_site = urllib.parse.quote(site, safe="")
    url_api = f"https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
    payload = {"inspectionUrl": url, "siteUrl": site}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url_api, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            ir = result.get("inspectionResult", {})
            return {
                "url": url,
                "verdict": ir.get("indexStatusResult", {}).get("verdict", "unknown"),
                "coverage": ir.get("indexStatusResult", {}).get("coverageState", "unknown"),
                "last_crawl": ir.get("indexStatusResult", {}).get("lastCrawlTime", ""),
                "mobile_usability": ir.get("mobileUsabilityResult", {}).get("verdict", "unknown"),
                "rich_results": [r.get("resultType") for r in ir.get("richResultsResult", {}).get("detectedItems", [])],
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        return {"url": url, "error": f"HTTP {e.code}: {body}"}


class URLInspector:
    """
    VECTOR's URL Inspection client.
    Checks per-page indexing status, mobile usability, and rich results.
    """

    def __init__(self) -> None:
        self._token: str | None = None

    def inspect_urls(self, site: str, urls: list[str], max_workers: int = 5) -> list[dict]:
        """Inspect multiple URLs concurrently. Returns list of inspection results."""
        token = _get_access_token()
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {pool.submit(_inspect_url, site, url, token): url for url in urls}
            for fut in futs:
                try:
                    results.append(fut.result(timeout=30))
                except Exception as e:
                    results.append({"url": futs[fut], "error": str(e)})
        logger.info("[VECTOR][gsc] inspected {} URLs for {}", len(results), site)
        return results

    def find_not_indexed(self, site: str, urls: list[str]) -> list[dict]:
        """Return only URLs that are not indexed or have coverage issues."""
        all_results = self.inspect_urls(site, urls)
        return [
            r for r in all_results
            if r.get("verdict", "").lower() not in ("pass", "valid")
            and "error" not in r
        ]

    async def inspect_async(self, site: str, urls: list[str]) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.inspect_urls, site, urls)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    client = GSCClient()
    inspector = URLInspector()
    print("OK gsc_client.py — GSCClient + URLInspector ready (requires gcloud auth)")
    print(f"  GSCClient: list_sites(), fetch(site, days), analyze(data), fetch_and_analyze(site)")
    print(f"  URLInspector: inspect_urls(site, urls), find_not_indexed(site, urls)")
