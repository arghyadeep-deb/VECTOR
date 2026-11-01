"""Migrate secrets from .env file to OS keyring.

Usage:
    python scripts/migrate_secrets_to_keyring.py              # dry run (show what would be migrated)
    python scripts/migrate_secrets_to_keyring.py --apply      # actually migrate
    python scripts/migrate_secrets_to_keyring.py --audit      # audit current secret strength

After migration, secrets are read from keyring as fallback when .env doesn't have them.
The .env file can be deleted once all secrets are in keyring.

Security: keyring uses OS-level credential storage:
    - Windows: Credential Manager (DPAPI-encrypted)
    - macOS: Keychain
    - Linux: Secret Service (GNOME Keyring / KWallet)
"""

from __future__ import annotations

import sys
from pathlib import Path

_this_dir = Path(__file__).resolve().parent
_repo_root = _this_dir.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import argparse
import os
import secrets

from dotenv import dotenv_values

from core.security.secrets_manager import (
    audit_secret,
    get_secret,
    record_secret_event,
    _keyring_set,
    _keyring_get,
    _SERVICE_NAME,
)
from loguru import logger


# Secrets to migrate — all VECTOR-specific keys and tokens
_SECRET_NAMES = [
    # Auth
    "VECTOR_API_KEY",
    "VECTOR_JWT_SECRET",
    "VECTOR_DB_KEY",
    # LLM providers
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY",
    "FIREWORKS_API_KEY",
    "PERPLEXITY_API_KEY",
    "COHERE_API_KEY",
    "CEREBRAS_API_KEY",
    "SAMNOVA_API_KEY",
    "NVIDIA_API_KEY",
    "MOONSHOT_API_KEY",
    "ZHIPU_API_KEY",
    # Integrations
    "GITHUB_TOKEN",
    "PUSHOVER_TOKEN",
    "PUSHOVER_USER",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "ELEVENLABS_KEY",
    "INSTAGRAM_ACCESS_TOKEN",
    "YOUTUBE_DATA_API_KEY",
    "HASS_TOKEN",
    # OAuth
    "OAUTH_GITHUB_CLIENT_SECRET",
    "OAUTH_GOOGLE_CLIENT_SECRET",
    # Notifications
    "SLACK_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    # Trading
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
]


def _load_env_secrets() -> dict[str, str]:
    """Load secrets from .env file."""
    env_path = _repo_root / ".env"
    if not env_path.exists():
        logger.warning("[VECTOR][secrets] .env file not found at {}", env_path)
        return {}
    values = dotenv_values(str(env_path))
    return {k: v for k, v in values.items() if v and v.strip()}


def _dry_run(env_secrets: dict[str, str]) -> None:
    """Show what would be migrated without actually doing it."""
    print(f"\n{'='*60}")
    print(f"DRY RUN — Secrets to migrate from .env to keyring")
    print(f"{'='*60}\n")

    to_migrate = []
    already_in_keyring = []
    missing = []

    for name in _SECRET_NAMES:
        env_val = env_secrets.get(name, "")
        kr_val = _keyring_get(name)

        if env_val:
            if kr_val:
                already_in_keyring.append(name)
            else:
                to_migrate.append(name)

    # Also check for env secrets not in our list
    extra = [k for k in env_secrets if k not in _SECRET_NAMES and
             any(s in k.upper() for s in ("KEY", "SECRET", "TOKEN", "PASS"))]

    print(f"To migrate ({len(to_migrate)}):")
    for name in to_migrate:
        val = env_secrets[name]
        print(f"  {name} ({len(val)} chars, source=.env)")

    if already_in_keyring:
        print(f"\nAlready in keyring ({len(already_in_keyring)}):")
        for name in already_in_keyring:
            print(f"  {name}")

    if extra:
        print(f"\nAdditional secrets in .env (not in migration list):")
        for name in extra:
            val = env_secrets[name]
            print(f"  {name} ({len(val)} chars)")

    print(f"\n{'='*60}")
    print(f"Run with --apply to migrate {len(to_migrate)} secrets to keyring")
    print(f"{'='*60}\n")


def _apply_migration(env_secrets: dict[str, str]) -> None:
    """Actually migrate secrets to keyring."""
    print(f"\n{'='*60}")
    print(f"MIGRATING secrets from .env to keyring ({_SERVICE_NAME})")
    print(f"{'='*60}\n")

    migrated = 0
    skipped = 0
    failed = 0

    for name in _SECRET_NAMES:
        env_val = env_secrets.get(name, "")
        if not env_val:
            continue

        kr_val = _keyring_get(name)
        if kr_val:
            print(f"  SKIP {name} (already in keyring)")
            skipped += 1
            continue

        ok = _keyring_set(name, env_val)
        if ok:
            # Verify it was stored
            verify = _keyring_get(name)
            if verify is not None and secrets.compare_digest(verify, env_val):
                print(f"  OK   {name} ({len(env_val)} chars → keyring)")
                record_secret_event("migrated", name, "env→keyring", True)
                migrated += 1
            else:
                print(f"  FAIL {name} (stored but verification failed)")
                failed += 1
        else:
            print(f"  FAIL {name} (keyring write failed)")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {migrated} migrated, {skipped} skipped, {failed} failed")
    print(f"{'='*60}")

    if migrated > 0:
        print(f"\nNext steps:")
        print(f"  1. Test that VECTOR still works (secrets now read from keyring)")
        print(f"  2. Once confirmed, delete or empty the .env file")
        print(f"  3. Run 'python scripts/migrate_secrets_to_keyring.py --audit' to verify")
    if failed > 0:
        print(f"\nTroubleshooting failed migrations:")
        print(f"  - Windows: Ensure Credential Manager service is running")
        print(f"  - Linux: Ensure gnome-keyring-daemon or kwallet is running")
        print(f"  - macOS: Keychain should work automatically")
    print()


def _audit_secrets() -> None:
    """Audit all configured secrets for strength."""
    print(f"\n{'='*60}")
    print(f"SECRET AUDIT")
    print(f"{'='*60}\n")

    configured = 0
    strong = 0
    weak = 0

    for name in _SECRET_NAMES:
        result = audit_secret(name)
        if result.configured:
            configured += 1
            status = "STRONG" if result.strong else "WEAK"
            if result.strong:
                strong += 1
            else:
                weak += 1
            print(f"  [{status:6s}] {name:40s} source={result.source:8s} len={result.length}")

    print(f"\n{'='*60}")
    print(f"Summary: {configured} configured, {strong} strong, {weak} weak")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Migrate VECTOR secrets from .env to OS keyring")
    parser.add_argument("--apply", action="store_true", help="Actually migrate (default: dry run)")
    parser.add_argument("--audit", action="store_true", help="Audit secret strength")
    args = parser.parse_args()

    env_secrets = _load_env_secrets()

    if args.audit:
        _audit_secrets()
    elif args.apply:
        if not env_secrets:
            print("No secrets found in .env file. Nothing to migrate.")
            sys.exit(0)
        _apply_migration(env_secrets)
    else:
        _dry_run(env_secrets)
