# Audit: Trading Analyst + Research/Scraping Agents
> 2026-07-07, Fable 5. Verdict per task: "if fine it's okay; otherwise optimize."

## Verdict summary
**Trading: FINE (safety-first by design) — one optimization applied.**
**Research/scraping: FINE (substantial, real backends) — no changes needed.**
Neither was deficient. I applied a low-risk model-routing optimization to the
investment LLM agents and left the rest as-is.

## Trading / investment district (`districts/investment/`)
Reviewed: stock_analyst, fundamentals_bot, technical_bot, sentiment_bot,
execution_engine, safety, backtest_agent, order_lifecycle, trading_conductor,
finagent/hedgebot, akshare/mootdx fetchers, alert_monitor, trading_calendar.

**Strengths (why it's fine):**
- **Safety-first, correct for "analysis-only, never auto-trades":**
  - `execution_engine.py` — paper-first: `CONFIG["investment"]["paper_trading"]`
    defaults True; documented SAFETY RULES; real orders require permission
    gateway RED-tier owner confirmation; daily counters/caps.
  - `safety.py::approve_live_trade` — kill switch (`status=blocked`), paper mode
    (`status=paper`), and gateway gating before any live order. Redacts secrets.
- **Real data with graceful fallbacks:** stock_analyst quote chain is
  yfinance → Yahoo HTTP → NSE/BSE → mock; TTL cache (300s). fundamentals via
  akshare/mootdx (A-share) + yfinance.
- All LLM calls go through `provider_client` (cloud-primary), never raw httpx.

**Optimization APPLIED (2026-07-07):** the LLM agents used generic
`tier="reasoning"`. Switched the flagship + sentiment to
`model="domain:finance.analysis"` (chain: github/gpt-5 → cerebras/zai-glm-4.7
355B → github/DeepSeek-R1 → groq/llama-3.3-70b → ollama/vector-reasoning). This
gives finance-tuned model selection instead of a generic tier. Files:
`stock_analyst.py`, `sentiment_bot.py`. Syntax-verified.

**RECOMMENDED (not blocking, do if desired):** apply the same one-line
`model="domain:finance.analysis"` to any other investment agent that calls
`_PC().chat(..., tier="reasoning"/"agentic")` — e.g. fundamentals_bot/
technical_bot if/when they add LLM calls, finagent/hedgebot. Grep:
`grep -rn 'tier="reasoning"' districts/investment/`. Low risk (domain chains
always terminate on ollama).

**No deficiencies found.** Do NOT rip out or rewrite — it's correct and safe.

## Research engine (`core/research_engine/`)
A full research subsystem: `auto_research_agent`, `search_system` (+ factory),
`report_generator`/`report_assembler`, `citation_handler`, `result_analyzer`,
`experiment_designer`, `sandbox_executor` (sandboxed code exec),
advanced_search_system strategies. Substantial and real. LLM-backed design gated
behind `VECTOR_RESEARCH_LLM_DESIGN` (now enabled 2026-07-04).
**Verdict: fine, no changes.**

## Research district agents (`districts/research/`)
`web_scout` — already uses `domain="research"` routing (gated behind
`VECTOR_WEB_SCOUT_LLM`, now enabled). paper_reader, news_aggregator,
reddit_miner, opencli_adapter present. Free connectors (HN/Reddit/GitHub) work;
paid ones (Twitter/TikTok/IG) owner-gated. **Verdict: fine.**

## Scraper (`core/scraper/`)
`vector_scraper` + engines/spiders + toolbelt (ad_domains, checkpoint, request).
Substantial. **Verdict: fine, no changes.**

## What remains uncertain / not deep-audited
- Did not run live trading/backtest end-to-end (would need market data + paper
  broker config). The safety gating is verified by code read, not live execution.
- Did not benchmark research-engine output quality (subjective; needs a task).

## Provenance
2026-07-07 code read. Re-verify safety: `grep -n "paper_trading" districts/investment/execution_engine.py`.
Re-verify finance domain: `python -c "from core.inference.model_catalog import chain_for_domain; print(chain_for_domain('finance.analysis'))"`.
