"""
VECTOR Autonomous Hands — pre-built scheduled agent packages.

Each Hand is a complete autonomous capability:
  - System prompt (multi-phase, 500+ words)
  - Tool allowlist
  - Schedule (cron expression)
  - Guardrails and approval gates
  - Output format

9 Hands ported and VECTOR-branded:
  researcher     : deep multi-phase research with credibility scoring
  collector      : OSINT + change detection + sentiment alerts
  predictor      : superforecasting with Brier score tracking
  browser        : web automation with purchase approval gate
  trader         : crypto analysis (analysis only, never trades)
  lead           : prospect discovery with ICP scoring
  content        : social media content generation (7 formats)
  clip           : video → vertical shorts pipeline
  vault_sync     : secrets management sync
"""
from agents.hands.registry import HandRegistry, Hand, get_hand, list_hands, get_all_hands
__all__ = ["HandRegistry", "Hand", "get_hand", "list_hands", "get_all_hands"]
