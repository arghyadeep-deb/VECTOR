"""Phase 0 of plans/wire-absorbed-repos-autonomy.md.

Two independent, evidence-based checks per absorbed-repo capability:

  --reachability     importlib-import every target module for each repo;
                      report RESOLVES vs IMPORT_ERROR. Writes
                      docs/capability_proofs/_reachability.md.

  --live <repo>       invoke the real district entrypoint ONCE with a
                      minimal real input (no mocks). Captures the verbatim
                      result/traceback and a verdict:
                        LIVE         — produced real, non-empty output
                        NEEDS-CONFIG — ran but needs an API key / data source
                        BROKEN       — raised; traceback recorded
                      Writes docs/capability_proofs/<repo>.md.

Usage:
    PYTHONUTF8=1 python scripts/capability_smoke.py --reachability
    PYTHONUTF8=1 python scripts/capability_smoke.py --live research_engine
    PYTHONUTF8=1 python scripts/capability_smoke.py --live all
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# run_vector.py (the real production entrypoint) loads .env at startup;
# this standalone script didn't, so env-only fixes (e.g. VECTORINTEL_HOST)
# looked broken here while actually working fine in production. Match
# production's behavior so this tool's verdicts are trustworthy.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent


def _use_isolated_db() -> None:
    """--live must not fight a real, already-running VECTOR process over the
    shared SQLCipher DB file (Phase 0 hit exactly this: a leftover
    `run_vector.py api` process held the file, and any second process trying
    to open it got a deterministic 'hmac check failed' error).

    core.memory.db_utils.configured_db_path() already honors VECTOR_DB_PATH
    for exactly this purpose ("repair/tests") — point it at a fresh temp file
    so every --live run gets its own isolated DB. Must run before any VECTOR
    module is imported (the DB connection is a module-level singleton)."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="vector_capability_smoke_"))
    os.environ["VECTOR_DB_PATH"] = str(tmp_dir / "smoke_memory.db")
PROOFS_DIR = ROOT / "docs" / "capability_proofs"

REACHABILITY_TARGETS: dict[str, list[str]] = {
    "investment": [
        "districts.investment.finagent_agent",
        "districts.investment.trading_conductor_agent",
        "districts.investment.backtest_agent",
        "districts.investment.hedgebot_agent",
    ],
    "research_engine": [
        "core.research_engine.auto_research_agent",
        "core.research_engine.experiment_designer",
        "core.research_engine.sandbox_executor",
        "core.research_engine.result_analyzer",
        "core.research_engine.report_assembler",
    ],
    "research_district": [
        "districts.research.agent",
        "districts.research.deep_researcher",
        "districts.research.news_aggregator",
        "districts.research.paper_reader",
        "districts.research.reddit_miner",
        "districts.research.research_hub",
        "districts.research.stealth_scout_agent",
        "districts.research.web_scout",
        "districts.research.opencli_adapter",
        "districts.research.api_catalog",
        "districts.research.research_api",
    ],
    "scraper": [
        "core.scraper.vector_scraper",
    ],
    "trading": [
        "core.trading.crypto_trading",
        "core.trading.config",
    ],
    "coding_assistant": [
        "districts.coding.coding_tools",
    ],
    "intelligence": [
        "districts.intelligence.social_sim_agent",
        "districts.intelligence.vectorintel_agent",
    ],
}


def check_reachability() -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {}
    for repo, modules in REACHABILITY_TARGETS.items():
        repo_result = []
        for mod in modules:
            try:
                importlib.import_module(mod)
                repo_result.append({"module": mod, "status": "RESOLVES"})
            except Exception as e:
                repo_result.append({
                    "module": mod,
                    "status": "IMPORT_ERROR",
                    "error": f"{type(e).__name__}: {e}",
                })
        results[repo] = repo_result
    return results


def write_reachability_md(results: dict[str, list[dict]]) -> Path:
    PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    out = PROOFS_DIR / "_reachability.md"
    lines = [
        "# Capability Reachability Map",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Each absorbed-repo entrypoint module, import-resolved via `importlib`.",
        "RESOLVES = imports cleanly with no error. IMPORT_ERROR = breaks before "
        "any code can run (this is a stronger finding than 'unreached' — it "
        "means the capability cannot work at all right now).",
        "",
    ]
    total_ok = total_n = 0
    for repo, modules in results.items():
        resolved = sum(1 for m in modules if m["status"] == "RESOLVES")
        total_ok += resolved
        total_n += len(modules)
        lines.append(f"## {repo} — {resolved}/{len(modules)} resolve")
        lines.append("")
        lines.append("| Module | Status | Error |")
        lines.append("|---|---|---|")
        for m in modules:
            err = m.get("error", "").replace("|", "\\|")
            lines.append(f"| `{m['module']}` | {m['status']} | {err} |")
        lines.append("")
    lines.insert(4, f"**Totals: {total_ok}/{total_n} modules resolve.**\n")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ── Live capability probes — one real, minimal invocation each ─────────────

async def _live_research_engine() -> dict:
    from core.research_engine.auto_research_agent import AutoResearchAgent
    agent = AutoResearchAgent()
    report = agent.run_full_cycle("test")
    return {
        "report_id": getattr(report, "id", None),
        "sections": len(getattr(report, "sections", []) or []),
        "title": getattr(report, "title", None),
    }


async def _live_investment() -> dict:
    from districts.investment.finagent_agent import FinAgentAgent
    agent = FinAgentAgent()
    return await agent.run({
        "params": {"action": "investor_analysis", "ticker": "AAPL", "persona": "buffett"}
    })


async def _live_trading() -> dict:
    from districts.investment.trading_conductor_agent import TradingConductorAgent
    agent = TradingConductorAgent()
    return await agent.run({
        "params": {"action": "market_research", "ticker": "AAPL"}
    })


async def _live_scraper() -> dict:
    from core.scraper.vector_scraper import VectorScraper
    scraper = VectorScraper()
    result = await scraper.fetch("https://example.com")
    return {
        "status_code": getattr(result, "status_code", None),
        "content_len": len(getattr(result, "content", "") or ""),
        "url": getattr(result, "url", None),
    }


async def _live_intelligence() -> dict:
    from districts.intelligence.vectorintel_agent import VectorIntelAgent
    agent = VectorIntelAgent()
    return await agent.get_flights(lat=28.6, lon=77.2, radius_km=500)


async def _live_coding_assistant() -> dict:
    from districts.coding.coding_tools import grep_code
    result = grep_code("class ", path="core/city", file_glob="*.py")
    return result


LIVE_PROBES: dict[str, callable] = {
    "research_engine": _live_research_engine,
    "investment": _live_investment,
    "trading": _live_trading,
    "scraper": _live_scraper,
    "intelligence": _live_intelligence,
    "coding_assistant": _live_coding_assistant,
}

# Substrings in an exception that strongly indicate "needs config" rather
# than "broken" — missing key/credential/network, not a code defect.
_NEEDS_CONFIG_HINTS = (
    "api_key", "apikey", "api key", "credential", "token", "auth",
    "no such file", "not found", "environment variable", "env var",
    "connection refused", "timeout", "name resolution", "getaddrinfo",
    "ssl", "certificate", "rate limit", "quota", "unauthorized", "403",
    "401", "network is unreachable",
)


def _classify(output, error: str | None) -> str:
    if error:
        low = error.lower()
        if any(h in low for h in _NEEDS_CONFIG_HINTS):
            return "NEEDS-CONFIG"
        return "BROKEN"
    if output is None:
        return "BROKEN"
    if isinstance(output, dict):
        if output.get("status") == "error":
            err = str(output.get("error", "")).lower()
            if any(h in err for h in _NEEDS_CONFIG_HINTS):
                return "NEEDS-CONFIG"
            return "BROKEN"
        # Non-error dict with no real content is suspicious but not proof of
        # brokenness — require at least one non-trivial value.
        meaningful = any(
            v not in (None, "", [], {}, 0) for k, v in output.items() if k != "status"
        )
        if not meaningful:
            return "BROKEN"
    return "LIVE"


async def run_live(repo: str) -> dict:
    probe = LIVE_PROBES.get(repo)
    if probe is None:
        return {"repo": repo, "verdict": "BROKEN", "error": f"no live probe defined for '{repo}'"}

    started = datetime.now(timezone.utc).isoformat()
    output = None
    error = None
    tb = None
    try:
        output = await probe()
    except Exception:
        tb = traceback.format_exc()
        error = tb.strip().splitlines()[-1] if tb else "unknown error"

    verdict = _classify(output, error)
    return {
        "repo": repo,
        "verdict": verdict,
        "started": started,
        "output": output,
        "error": error,
        "traceback": tb,
    }


def write_live_md(result: dict) -> Path:
    PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    out = PROOFS_DIR / f"{result['repo']}.md"
    lines = [
        f"# Capability Proof — {result['repo']}",
        "",
        f"**Verdict: {result['verdict']}**",
        "",
        f"Run at: {result['started']}",
        "",
    ]
    if result["output"] is not None:
        lines += ["## Output (verbatim)", "", "```", repr(result["output"]), "```", ""]
    if result["error"]:
        lines += ["## Error", "", f"`{result['error']}`", ""]
    if result["traceback"]:
        lines += ["## Traceback", "", "```", result["traceback"].rstrip(), "```", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reachability", action="store_true")
    parser.add_argument("--live", metavar="REPO", help="repo name, or 'all'")
    args = parser.parse_args()

    failed = False
    if args.reachability:
        results = check_reachability()
        out = write_reachability_md(results)
        print(f"wrote {out}")
        for repo, modules in results.items():
            resolved = sum(1 for m in modules if m["status"] == "RESOLVES")
            print(f"  {repo}: {resolved}/{len(modules)} resolve")
            failed = failed or resolved != len(modules)

    if args.live:
        _use_isolated_db()
        repos = list(LIVE_PROBES) if args.live == "all" else [args.live]
        for repo in repos:
            print(f"--- live: {repo} ---")
            result = asyncio.run(run_live(repo))
            out = write_live_md(result)
            print(f"  verdict={result['verdict']}  -> {out}")
            if result["error"]:
                print(f"  error: {result['error']}")
            failed = failed or result["verdict"] == "BROKEN"

    if not args.reachability and not args.live:
        parser.print_help()
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
