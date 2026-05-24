"""
vc_env.py — Centralized environment variable access for vectorcode/src/.

All env reads in vectorcode/src/ should go through os.environ.get() or
import specific constants from this module. This module is the single
source of truth for what env vars the vectorcode layer needs.

RULE 11 compliance: API keys must never be hardcoded. They come from
.env (loaded by run_vector.py via python-dotenv) or CI secrets.
"""
from __future__ import annotations

import os

# ── Core VECTOR config ───────────────────────────────────────────────────────
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
VECTORINTEL_HOST: str = os.environ.get("VECTORINTEL_HOST", "http://127.0.0.1:8002")
VECTOR_ENV: str = os.environ.get("VECTOR_ENV", "development")

# ── LLM provider API keys ────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
MISTRAL_API_KEY: str = os.environ.get("MISTRAL_API_KEY", "")

# ── Communication platform tokens ────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK: str = os.environ.get("DISCORD_WEBHOOK", "")
DISCORD_BOT_TOKEN: str = os.environ.get("DISCORD_BOT_TOKEN", "")
SLACK_BOT_TOKEN: str = os.environ.get("SLACK_BOT_TOKEN", "")
WHATSAPP_TOKEN: str = os.environ.get("WHATSAPP_TOKEN", "")

# ── Database / storage ───────────────────────────────────────────────────────
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")
DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

# ── Notifications ────────────────────────────────────────────────────────────
PUSHOVER_USER_KEY: str = os.environ.get("PUSHOVER_USER_KEY", "")
PUSHOVER_API_TOKEN: str = os.environ.get("PUSHOVER_API_TOKEN", "")
TWILIO_ACCOUNT_SID: str = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.environ.get("TWILIO_AUTH_TOKEN", "")

# ── Convenience helper (use os.environ.get directly for new code) ─────────────
def get_env(key: str, default: str | None = None) -> str | None:
    """Read an environment variable. Prefer direct os.environ.get in new code."""
    return os.environ.get(key, default)


if __name__ == "__main__":
    print("vc_env OK — OLLAMA_HOST:", OLLAMA_HOST)
