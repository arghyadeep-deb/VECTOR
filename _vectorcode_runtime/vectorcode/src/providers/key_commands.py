"""Named user API-key setup for the VectorCode launcher."""

import warnings
from getpass import GetPassWarning, getpass

from loguru import logger

from vectorcode.src.cli.auth import _ENV_PATTERNS, AuthManager
from vectorcode.src.providers.coding_catalog import get_coding_provider as get_provider


def handle_auth(args):
    action = getattr(args, "auth_action", None) or "list"
    manager = AuthManager()
    if action == "add":
        provider = args.provider.strip().lower()
        if provider == "google":
            provider = "gemini"
        try:
            definition = get_provider(provider)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        if not definition or definition.driver not in {"openai_compat", "anthropic", "gemini"}:
            raise SystemExit("Unsupported coding provider; use OpenAI-compatible, anthropic or gemini.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", GetPassWarning)
                key = (getattr(args, "key", None) or getpass("Paste your API key (hidden): ")).strip()
        except GetPassWarning:
            raise SystemExit('A secure terminal is required for hidden API-key entry.') from None
        if not key or any(character.isspace() for character in key):
            raise SystemExit("API key must be non-empty and contain no whitespace.")
        manager.add(args.name, provider, key, require_keyring=True)
        logger.success("Credential saved in system keyring. Select --model {}/<model-id>.", provider)
    elif action == "list":
        entries = manager.list_credentials()
        for entry in entries:
            logger.info("{}: {} ({})", entry.name, entry.provider, entry.source)
        if not entries:
            logger.info("No stored API keys. Use vector auth add <name> --provider <provider>.")
    elif action == "remove":
        result = manager.remove(args.name)
        logger.info("Credential removed." if result["removed"] else "Credential not found.")
    elif action == "test":
        result = manager.test(args.name)
        logger.info("Credential check: {}", "valid" if result.get("valid") else "failed or unsupported")
    elif action == "from-env":
        import os

        count = 0
        for variable, provider in _ENV_PATTERNS.items():
            try:
                definition = get_provider(provider)
            except ValueError:
                continue
            key = os.environ.get(variable, "").strip()
            if key and definition and definition.driver in {"openai_compat", "anthropic", "gemini"}:
                manager.add(variable.lower(), provider, key, require_keyring=True)
                count += 1
        logger.info("Imported {} credentials into system keyring.", count)
    else:
        raise SystemExit(f"Unknown auth action: {action}")


if __name__ == "__main__":
    assert get_provider("anthropic").driver == "anthropic"
    assert get_provider("freellmapi").api_key_env == "FREELLMAPI_API_KEY"
