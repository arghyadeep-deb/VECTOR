# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
**Confirmed upstream (2026-10-12):** `HKUDS/Vibe-Trading` (PyPI package `vibe-trading-ai`).
License: **MIT** (per upstream's root `LICENSE`; restored locally at `LICENSE` in this
directory, 2026-10-13).
Root `SKILL.md`'s front matter names `vibe-trading` version `0.1.7` and requires
`vibe-trading-ai`; it describes the same seven engines, six data sources, 74 skills,
29 swarm teams, Shadow Account workflow, CLI, API, and MCP commands present in this tree.
Version `0.1.7` is the best local pin marker; later local content may exceed that release.
It appears to be a standalone backtesting framework, with its own `src/`, `runs/`, `sessions/`, and `tests/` layout.
VECTOR uses selected backtesting utilities rather than treating this tree as native VECTOR code.
`BacktestAgent` imports `AgentLoop`, `ChatLLM`, `build_registry`, and `PersistentMemory` from this tree.
It also invokes the tree's configured backtesting engines.
Vendored as-is; VECTOR's own code calls into: `districts/investment/backtest_agent.py`.

## Owner disposition (2026-10-12)

Option (2), pinned external dependency — its 565-file size and self-contained layout favor
an explicit upstream revision/version record, preserved MIT license, local-patch ledger,
and update/vulnerability-monitoring policy over recurring line-by-line review. Keep
focused reachability tests around the wrapper and Permission Gateway, since generated
strategy code is privileged. See
`docs/design/investigation-2026-10-12-vector-backtest-origin.md` for the full
provenance investigation.
