"""
VECTOR × public-apis catalog scanner.

Parses the public-apis README.md to build a searchable catalog of 1000+ free APIs.
ResearchHub uses this to auto-discover data sources for any research topic.

Source: C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/public-apis_public-apis/repo/README.md
"""
import re
import sys
from pathlib import Path
from functools import lru_cache

_README = Path(__file__).parent.parent.parent.parent / "GitHub" / "public-apis-master" / "README.md"
if not _README.exists():
    # Try alternate naming convention used by older clone
    _README_ALT = Path(__file__).parent.parent.parent.parent.parent / \
        "GitHub/public-apis_public-apis/repo/README.md"
    if _README_ALT.exists():
        _README = _README_ALT

from loguru import logger


@lru_cache(maxsize=1)
def _load_catalog() -> list[dict]:
    """Parse the public-apis README into a list of API entries. Cached after first load."""
    if not _README.exists():
        logger.warning(f"[PublicAPIs] README not found at {_README}")
        return []

    text = _README.read_text(encoding="utf-8", errors="ignore")
    apis = []
    current_category = ""

    for line in text.splitlines():
        # Category header: ## Animals
        if line.startswith("## "):
            current_category = line[3:].strip()
            continue

        # Table row: | API Name | Description | Auth | HTTPS | CORS | Link |
        if line.startswith("| ") and " | " in line:
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]  # remove empty
            if len(parts) >= 4 and parts[0].lower() not in ("api", "---"):
                name = parts[0]
                description = parts[1] if len(parts) > 1 else ""
                auth = parts[2] if len(parts) > 2 else ""
                https = parts[3] if len(parts) > 3 else ""
                cors = parts[4] if len(parts) > 4 else ""
                link = parts[5] if len(parts) > 5 else ""

                # Extract URL from markdown link [text](url)
                url_match = re.search(r'\(https?://[^\)]+\)', link)
                url = url_match.group()[1:-1] if url_match else ""

                if name and description and name != "---":
                    apis.append({
                        "name": name,
                        "description": description,
                        "category": current_category,
                        "auth": auth,
                        "https": https.lower() == "yes",
                        "cors": cors,
                        "url": url,
                        "free": auth.lower() in ("no", "", "apikey"),
                    })

    logger.info(f"[PublicAPIs] Loaded {len(apis)} APIs from catalog")
    return apis


def search_apis(query: str, category: str = "", free_only: bool = True, limit: int = 10) -> list[dict]:
    """
    Search the public-apis catalog by keyword and optional category.
    Returns APIs relevant to the query — ResearchHub uses this to find data sources.
    """
    catalog = _load_catalog()
    query_lower = query.lower()
    results = []

    for api in catalog:
        if free_only and not api["free"]:
            continue
        if category and category.lower() not in api["category"].lower():
            continue

        # Score by relevance
        score = 0
        if query_lower in api["name"].lower():
            score += 3
        if query_lower in api["description"].lower():
            score += 2
        if query_lower in api["category"].lower():
            score += 1

        if score > 0:
            results.append({**api, "_score": score})

    results.sort(key=lambda x: x["_score"], reverse=True)
    return [{k: v for k, v in r.items() if k != "_score"} for r in results[:limit]]


def get_categories() -> list[str]:
    """List all API categories in the catalog."""
    catalog = _load_catalog()
    return sorted(set(a["category"] for a in catalog if a["category"]))


def get_by_category(category: str, free_only: bool = True) -> list[dict]:
    """Get all APIs in a specific category."""
    catalog = _load_catalog()
    return [
        a for a in catalog
        if category.lower() in a["category"].lower()
        and (not free_only or a["free"])
    ]


def get_stats() -> dict:
    """Catalog statistics."""
    catalog = _load_catalog()
    categories = {}
    for a in catalog:
        categories[a["category"]] = categories.get(a["category"], 0) + 1
    return {
        "total": len(catalog),
        "free": sum(1 for a in catalog if a["free"]),
        "categories": len(categories),
        "top_categories": sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10],
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    stats = get_stats()
    print(f"Catalog: {stats['total']} APIs, {stats['free']} free, {stats['categories']} categories")

    results = search_apis("weather", free_only=True, limit=5)
    print(f"\nWeather APIs ({len(results)}):")
    for r in results:
        print(f"  {r['name']}: {r['description'][:60]}")

    results = search_apis("finance stock", free_only=True, limit=5)
    print(f"\nFinance APIs ({len(results)}):")
    for r in results:
        print(f"  {r['name']}: {r['description'][:60]}")
    print("✅ public_apis_catalog OK")
