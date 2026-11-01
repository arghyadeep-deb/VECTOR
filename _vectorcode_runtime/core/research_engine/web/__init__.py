"""Minimal clean-room stand-in for the missing research_engine `web` package.

Only the pieces other research_engine modules actually need at import time
are rebuilt here (currently: `models.settings`). The original `web` package
this absorbed subsystem assumed was a full Flask app (auth, themes, SocketIO,
PDF export) -- VECTOR never needed that (it has its own FastAPI app + HUD),
so the rest is deliberately not rebuilt. See docs/repo_analysis/_MASTER_TODO.md
§3 item 12 for the full investigation.
"""
