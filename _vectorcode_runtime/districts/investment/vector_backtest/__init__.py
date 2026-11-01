"""
VECTOR Quant Research — core/vibe_trading

Absorbed from open-source quant research platform. Provides:
- 74 finance skills (technical, options, crypto, macro, SEC/EDGAR, behavioral, ...)
- 9-engine backtest system (daily, A-shares, crypto, forex, futures, options, composite)
- Shadow Account engine (broker journal → ML behavior extraction → PDF report)
- 29 LangGraph swarm team presets
- 27 agent tools (factor analysis, options pricing, pattern recognition, ...)
- 22-tool MCP server
- ReAct finance research agent with cross-session memory

Usage via VECTOR governor:
  vt_research, vt_backtest, shadow_account, vt_swarm, vt_skills, vt_export
"""
import sys
from pathlib import Path

# Ensure src/ and backtest/ are importable (same pattern as original entry points)
_BACKTEST_DIR = Path(__file__).resolve().parent
if str(_BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKTEST_DIR))
