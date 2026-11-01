"""
VECTOR Ads Intelligence — core/ads

Multi-platform paid advertising audit, creative generation, and optimization.

Provides:
- analyze_landing  : Core Web Vitals + conversion signal analysis via Playwright
- capture_screenshot: Desktop/tablet/mobile screenshots
- fetch_page       : HTTP page downloader with redirect tracking + SSRF protection
- generate_image   : Multi-provider image generation (Gemini→OpenAI→Stability→Replicate)
- generate_report  : PDF audit report builder with matplotlib charts
- url_utils        : SSRF-safe URL validation

Platform coverage: Google Ads (80 checks), Meta (50), LinkedIn, TikTok, Microsoft,
YouTube, Apple Ads — 250+ weighted checks total.
"""

from pathlib import Path


_ADS_DIR = Path(__file__).parent
_SCRIPTS_DIR = _ADS_DIR / "scripts"
_REFERENCES_DIR = _ADS_DIR / "references"
_TEMPLATES_DIR = _ADS_DIR / "templates"


def ads_stats() -> dict:
    """Return basic stats about the VECTOR Ads module."""
    return {
        "scripts": len(list(_SCRIPTS_DIR.glob("*.py"))),
        "references": len(list(_REFERENCES_DIR.glob("*.md"))),
        "templates": len(list(_TEMPLATES_DIR.glob("*.md"))),
        "scripts_path": str(_SCRIPTS_DIR),
        "references_path": str(_REFERENCES_DIR),
        "templates_path": str(_TEMPLATES_DIR),
    }


def list_references() -> list[str]:
    """List all RAG knowledge reference documents."""
    return sorted(f.stem for f in _REFERENCES_DIR.glob("*.md"))


def list_templates() -> list[str]:
    """List all industry strategy templates."""
    return sorted(f.stem for f in _TEMPLATES_DIR.glob("*.md"))


def get_reference(name: str) -> str:
    """Read a reference document by stem name (e.g. 'google-audit')."""
    path = _REFERENCES_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Reference not found: {name}")
    return path.read_text(encoding="utf-8")


def get_template(name: str) -> str:
    """Read an industry template by stem name (e.g. 'saas')."""
    path = _TEMPLATES_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {name}")
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    stats = ads_stats()
    print("VECTOR Ads Intelligence")
    print(f"  Scripts:    {stats['scripts']}")
    print(f"  References: {stats['references']}")
    print(f"  Templates:  {stats['templates']}")
    print(f"\nReferences: {list_references()[:5]}...")
    print(f"Templates:  {list_templates()[:5]}...")
