"""Resolve explicit coding credentials without changing autonomous provider pools."""

from core.inference.llm_providers import get_provider
from core.security.secrets_manager import get_secret
from vectorcode.src.cli.auth import AuthManager
from vectorcode.src.providers.coding_catalog import get_coding_provider


def resolve_user_key(provider: str) -> str:
    manager = AuthManager()
    entries = [entry for entry in manager.list_credentials() if entry.provider == provider]
    if entries:
        entry = max(entries, key=lambda item: item.created_at)
        key = manager.get(entry.name)
        if not key:
            raise ValueError("Stored credential could not be retrieved; reconnect this provider.")
        return key
    definition = get_coding_provider(provider)
    key = get_secret(definition.api_key_env) if definition else ""
    if not key:
        raise ValueError(f"No key for {provider}; run vector auth add {provider} --provider {provider}.")
    return key


if __name__ == "__main__":
    assert get_provider("openai").api_key_env == "OPENAI_API_KEY"
