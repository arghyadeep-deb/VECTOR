# Third-Party Vendored Code Notice

This directory contains vendored third-party code.
It appears to be a standalone backtesting framework, with its own `src/`, `runs/`, `sessions/`, and `tests/` layout.
No root README, LICENSE, or `pyproject.toml` identifying an upstream project was found in this vendored tree.
Accordingly, no exact upstream project name is asserted here.
VECTOR uses selected backtesting utilities rather than treating this tree as native VECTOR code.
`BacktestAgent` imports `AgentLoop`, `ChatLLM`, `build_registry`, and `PersistentMemory` from this tree.
It also invokes the tree's configured backtesting engines.
Vendored as-is; VECTOR's own code calls into: `districts/investment/backtest_agent.py`.
