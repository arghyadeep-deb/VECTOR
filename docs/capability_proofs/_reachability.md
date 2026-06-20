# Capability Reachability Map

Generated: 2026-06-20T12:32:42.670486+00:00

**Totals: 26/26 modules resolve.**

Each absorbed-repo entrypoint module, import-resolved via `importlib`.
RESOLVES = imports cleanly with no error. IMPORT_ERROR = breaks before any code can run (this is a stronger finding than 'unreached' — it means the capability cannot work at all right now).

## investment — 4/4 resolve

| Module | Status | Error |
|---|---|---|
| `districts.investment.finagent_agent` | RESOLVES |  |
| `districts.investment.trading_conductor_agent` | RESOLVES |  |
| `districts.investment.backtest_agent` | RESOLVES |  |
| `districts.investment.hedgebot_agent` | RESOLVES |  |

## research_engine — 5/5 resolve

| Module | Status | Error |
|---|---|---|
| `core.research_engine.auto_research_agent` | RESOLVES |  |
| `core.research_engine.experiment_designer` | RESOLVES |  |
| `core.research_engine.sandbox_executor` | RESOLVES |  |
| `core.research_engine.result_analyzer` | RESOLVES |  |
| `core.research_engine.report_assembler` | RESOLVES |  |

## research_district — 11/11 resolve

| Module | Status | Error |
|---|---|---|
| `districts.research.agent` | RESOLVES |  |
| `districts.research.deep_researcher` | RESOLVES |  |
| `districts.research.news_aggregator` | RESOLVES |  |
| `districts.research.paper_reader` | RESOLVES |  |
| `districts.research.reddit_miner` | RESOLVES |  |
| `districts.research.research_hub` | RESOLVES |  |
| `districts.research.stealth_scout_agent` | RESOLVES |  |
| `districts.research.web_scout` | RESOLVES |  |
| `districts.research.opencli_adapter` | RESOLVES |  |
| `districts.research.api_catalog` | RESOLVES |  |
| `districts.research.research_api` | RESOLVES |  |

## scraper — 1/1 resolve

| Module | Status | Error |
|---|---|---|
| `core.scraper.vector_scraper` | RESOLVES |  |

## trading — 2/2 resolve

| Module | Status | Error |
|---|---|---|
| `core.trading.crypto_trading` | RESOLVES |  |
| `core.trading.config` | RESOLVES |  |

## coding_assistant — 1/1 resolve

| Module | Status | Error |
|---|---|---|
| `districts.coding.coding_tools` | RESOLVES |  |

## intelligence — 2/2 resolve

| Module | Status | Error |
|---|---|---|
| `districts.intelligence.social_sim_agent` | RESOLVES |  |
| `districts.intelligence.vectorintel_agent` | RESOLVES |  |
