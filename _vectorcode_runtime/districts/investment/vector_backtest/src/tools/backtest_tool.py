"""Backtest execution tool: validates config.json + signal_engine.py and runs the built-in engine."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from src.agent.tools import BaseTool
from src.core.runner import Runner
from src.tools.path_utils import safe_run_dir


def run_backtest(run_dir: str) -> str:
    """Run backtest: validate config.json + signal_engine.py, invoke built-in engine.

    RED-gated (58G remediation — VECTOR_TECHNICAL_KNOWLEDGE/58G_VECTOR_
    BACKTEST_REACT_TOOL_PERMISSION_REMEDIATION.md): this executes whatever
    module lives at run_path/code/signal_engine.py at call time — via
    dynamic import and instantiation inside the runner subprocess — with
    no sandbox, regardless of which upstream mechanism (the ReAct "backtest"
    tool, the "run_shadow_backtest" tool via shadow_account/backtester.py's
    run_backtest_fn injection point, or any future caller) produced that
    file or invoked this function. Gated here, at the single shared
    execution primitive, rather than at each of its callers individually,
    because that is the one chokepoint every real invocation path passes
    through — confirmed by a repo-wide search for every caller of this
    function before this change was made. Reuses the same "vt_backtest"
    RED action already established in Task 58E: the underlying consequence
    (executing a strategy engine through this exact runner) is identical
    regardless of which entry point reaches it, so a second action_type
    for the same operation was deliberately not introduced. Only harmless,
    read-only validation (path safety, config parsing, signal-file
    existence) may occur before this gate — no new persistence and no
    execution primitive is reached before it.

    Args:
        run_dir: Path to the run directory.

    Returns:
        JSON-formatted execution result.
    """
    try:
        run_path = safe_run_dir(run_dir)
    except ValueError as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

    config_path = run_path / "config.json"
    if not config_path.exists():
        return json.dumps({"status": "error", "error": "config.json not found"}, ensure_ascii=False)

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "error": f"config.json parse error: {e}"}, ensure_ascii=False)

    if "source" not in config:
        return json.dumps({"status": "error", "error": "config.json missing 'source' field (tushare/okx/yfinance)"}, ensure_ascii=False)

    valid_sources = {"tushare", "okx", "yfinance", "akshare", "ccxt", "auto"}
    if config["source"] not in valid_sources:
        return json.dumps({"status": "error", "error": f"source must be one of {valid_sources}, got: {config['source']}"}, ensure_ascii=False)

    signal_path = run_path / "code" / "signal_engine.py"
    if not signal_path.exists():
        return json.dumps({"status": "error", "error": "code/signal_engine.py not found"}, ensure_ascii=False)

    # ---- 58G gate: real permission boundary BEFORE any execution primitive ----
    try:
        strategy_source = signal_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return json.dumps({"status": "error", "error": f"could not read signal_engine.py: {exc}"}, ensure_ascii=False)

    strategy_digest = hashlib.sha256(strategy_source.encode("utf-8")).hexdigest()[:16]
    strategy_preview = strategy_source[:300]

    try:
        from core.loop.permission_gateway import PermissionGateway, Action

        gate_result = asyncio.run(PermissionGateway().execute(Action(
            action_type="vt_backtest",
            params={
                "run_dir": str(run_path),
                "codes": config.get("codes"),
                "engine": config.get("engine"),
                "source": config.get("source"),
                "has_strategy_code": True,
                "strategy_code_length": len(strategy_source),
                "strategy_code_sha256": strategy_digest,
                "strategy_code_preview": strategy_preview,
                "summary": (
                    f"Execute backtest strategy via the ReAct 'backtest' tool: "
                    f"run_dir={run_path}, engine={config.get('engine')!r}, "
                    f"source={config.get('source')!r} — runs "
                    f"{len(strategy_source)} chars of code (sha256:"
                    f"{strategy_digest}) at code/signal_engine.py, dynamically "
                    f"imported and instantiated by the backtest runner, no "
                    f"sandbox."
                ),
            },
            proposed_by="BacktestTool",
        )))
    except Exception as e:
        # Fail closed — never let a gateway-unreachable condition fall
        # through to a real backtest subprocess (mirrors hedgebot_agent.py's
        # solana_swap_execute pattern).
        return json.dumps({"status": "blocked", "reason": f"gateway unavailable: {e}"}, ensure_ascii=False)

    if not gate_result.approved:
        return json.dumps({"status": "blocked", "reason": gate_result.reason}, ensure_ascii=False)
    # ---- end 58G gate ----

    agent_root = Path(__file__).resolve().parents[2]
    entry_script = agent_root / "backtest" / "runner.py"

    runner = Runner(timeout=300)
    result = runner.execute(
        entry_script,
        run_path,
        cwd=agent_root,
        cli_args=[str(run_path)],
    )

    artifacts_found = {name: str(path) for name, path in result.artifacts.items()}
    return json.dumps({
        "status": "ok" if result.success else "error",
        "exit_code": result.exit_code,
        "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
        "stderr": result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        "artifacts": artifacts_found,
        "run_dir": run_dir,
    }, ensure_ascii=False)


class BacktestTool(BaseTool):
    """Backtest execution tool."""

    name = "backtest"
    description = "Run backtest: validate config.json + signal_engine.py, invoke built-in engine."
    parameters = {
        "type": "object",
        "properties": {
            "run_dir": {"type": "string", "description": "Path to the run directory"},
        },
        "required": ["run_dir"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs) -> str:
        """Execute backtest."""
        return run_backtest(kwargs["run_dir"])
