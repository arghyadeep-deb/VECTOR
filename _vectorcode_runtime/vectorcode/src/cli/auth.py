"""Credential management — add, remove, list, test API credentials."""
# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------

from pathlib import Path
import json
import hashlib
import os
import platform
import base64
import getpass
import datetime
import tempfile
from dataclasses import dataclass, asdict
from typing import Optional


from loguru import logger


class CredentialStoreCorruptedError(Exception):
    """~/.vector/credentials.json exists but could not be parsed (corrupted
    or malformed JSON). Distinct from "file doesn't exist" -- add()/remove()
    would otherwise silently treat a corrupted store as empty and overwrite
    it, destroying every other stored credential's metadata."""

@dataclass
class CredentialEntry:
    name: str          # e.g. "openai-work", "anthropic-personal"
    provider: str      # "anthropic", "openai", "ollama", "gemini", etc.
    key_hint: str      # Last 4 chars of key for display
    source: str        # "env", "keyring", "config"
    created_at: str

# Known API key environment variable patterns
_ENV_PATTERNS: dict[str, str] = {
    "ANTHROPIC_API_KEY":   "anthropic",
    "OPENAI_API_KEY":      "openai",
    "GEMINI_API_KEY":      "gemini",
    "GOOGLE_API_KEY":      "gemini",
    "COHERE_API_KEY":      "cohere",
    "MISTRAL_API_KEY":     "mistral",
    "TOGETHER_API_KEY":    "together",
    "GROQ_API_KEY":        "groq",
    "HUGGINGFACE_API_KEY": "huggingface",
    "FREELLMAPI_API_KEY":  "freellmapi",
}

# Provider → test endpoint config
_PROVIDER_TEST: dict[str, dict] = {
    "anthropic": {
        "url": "https://api.anthropic.com/v1/models",
        "headers_fn": lambda key: {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        "method": "GET",
    },
    "openai": {
        "url": "https://api.openai.com/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "method": "GET",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models",
        "headers_fn": lambda key: {},
        "params_fn": lambda key: {"key": key},
        "method": "GET",
    },
    "ollama": {
        "url": "http://localhost:11434/api/tags",
        "headers_fn": lambda key: {},
        "method": "GET",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "method": "GET",
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "method": "GET",
    },
    "cohere": {
        "url": "https://api.cohere.ai/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "method": "GET",
    },
    "together": {
        "url": "https://api.together.xyz/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "method": "GET",
    },
    "huggingface": {
        "url": "https://huggingface.co/api/whoami",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "method": "GET",
    },
}

def _machine_key() -> bytes:
    """Derive a machine-specific key from hostname. NOT cryptographically secure —
    this is obfuscation, not real encryption. Use system keyring for real security.
    """
    raw = platform.node().encode("utf-8") or b"vectorcode-default"
    return hashlib.sha256(raw).digest()  # 32 bytes

def _xor_obfuscate(data: bytes) -> str:
    """XOR-obfuscate bytes with machine key, return base64.
    Obfuscation only — not encryption. Prevents casual plaintext reads.
    """
    key = _machine_key()
    key_stream = (key[i % len(key)] for i in range(len(data)))
    obfuscated = bytes(a ^ b for a, b in zip(data, key_stream))
    return base64.b64encode(obfuscated).decode("utf-8")

def _xor_deobfuscate(encoded: str) -> bytes:
    """Reverse XOR obfuscation."""
    obfuscated = base64.b64decode(encoded.encode("utf-8"))
    key = _machine_key()
    key_stream = (key[i % len(key)] for i in range(len(obfuscated)))
    return bytes(a ^ b for a, b in zip(obfuscated, key_stream))

_auth_manager_instance: Optional["AuthManager"] = None

class AuthManager:
    """
    Manages API credentials for VectorCode providers.
    Storage priority:
      1. System keyring (via `keyring` package) — most secure
      2. XOR-obfuscated JSON file at ~/.vector/credentials.json — fallback
         (obfuscation only, not encryption — use keyring for real security)
    NEVER stores or logs plaintext keys.
    """

    STORAGE_PATH = Path.home() / ".vector" / "credentials.json"
    KEYRING_SERVICE = "vectorcode"

    def __init__(self) -> None:
        self._keyring_available = self._probe_keyring()
        logger.debug(f"[VECTOR][auth] keyring available: {self._keyring_available}")

    # ── Keyring probe ────────────────────────────────────────────

    def _probe_keyring(self) -> bool:
        try:
            import keyring  # noqa: F401
            return True
        except ImportError:
            return False

    # ── Internal storage helpers ─────────────────────────────────

    def _load_file_store(self) -> dict:
        """Load credentials from the file fallback store.

        Raises CredentialStoreCorruptedError if the file exists but isn't
        valid JSON -- returning {} here would make add()/remove() silently
        overwrite a corrupted store with "no credentials", destroying
        every other stored credential's metadata on the very next write.
        """
        if not self.STORAGE_PATH.exists():
            return {}
        try:
            raw = json.loads(self.STORAGE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            raise CredentialStoreCorruptedError(
                f"{self.STORAGE_PATH} exists but could not be parsed: {e}. "
                "Refusing to treat this as an empty credential store to "
                "avoid overwriting existing entries."
            ) from e
        return raw if isinstance(raw, dict) else {}

    def _save_file_store(self, store: dict) -> None:
        """Durably replace the file fallback store with restricted permissions."""
        self.STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.STORAGE_PATH.parent),
            prefix=f".{self.STORAGE_PATH.name}.",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(store, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                import stat
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception as _sve:
                logger.debug("[VECTOR][cli.auth] suppressed Exception: {}", _sve)
            os.replace(tmp_path, self.STORAGE_PATH)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    # ── Public API ───────────────────────────────────────────────

    def add(self, name: str, provider: str, api_key: str, *, require_keyring: bool = False) -> dict:
        """
        Store credential securely.
        1. Try system keyring.
        2. Fallback: XOR-obfuscate and store in ~/.vector/credentials.json.
        Returns {"name": name, "provider": provider, "stored": "keyring"|"file"}
        require_keyring refuses file fallback for the user-key coding setup.
        """
        hint = api_key[-4:] if len(api_key) >= 4 else "****"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if self._keyring_available:
            try:
                import keyring
                keyring.set_password(self.KEYRING_SERVICE, name, api_key)
                # Store metadata (no key) in file store
                store = self._load_file_store()
                store[name] = {
                    "provider": provider,
                    "hint": hint,
                    "source": "keyring",
                    "created_at": created_at,
                }
                self._save_file_store(store)
                logger.info(f"[VECTOR][auth] Stored '{name}' in system keyring")
                return {"name": name, "provider": provider, "stored": "keyring"}
            except Exception as e:
                if require_keyring:
                    raise RuntimeError("System keyring storage failed; key was not saved to a file.") from None
                logger.warning(f"[VECTOR][auth] Keyring store failed, falling back to file: {e}")

        # File fallback — obfuscate key
        if require_keyring:
            raise RuntimeError("System keyring is unavailable; install/configure keyring before saving a key.")
        store = self._load_file_store()
        store[name] = {
            "provider": provider,
            "hint": hint,
            "source": "file",
            "created_at": created_at,
            "_obfuscated": _xor_obfuscate(api_key.encode("utf-8")),
        }
        self._save_file_store(store)
        logger.info(f"[VECTOR][auth] Stored '{name}' in ~/.vector/credentials.json (obfuscated)")
        return {"name": name, "provider": provider, "stored": "file"}

    def remove(self, name: str) -> dict:
        """Remove credential from keyring and/or file store."""
        removed_from: list[str] = []

        if self._keyring_available:
            try:
                import keyring
                existing = keyring.get_password(self.KEYRING_SERVICE, name)
                if existing is not None:
                    keyring.delete_password(self.KEYRING_SERVICE, name)
                    removed_from.append("keyring")
            except Exception as e:
                logger.debug(f"[VECTOR][auth] Keyring remove error: {e}")

        store = self._load_file_store()
        if name in store:
            del store[name]
            self._save_file_store(store)
            removed_from.append("file")

        if not removed_from:
            return {"name": name, "removed": False, "error": "Credential not found"}
        return {"name": name, "removed": True, "sources": removed_from}

    def list_credentials(self) -> list[CredentialEntry]:
        """List all stored credentials — names and hints only, never full keys."""
        store = self._load_file_store()
        entries: list[CredentialEntry] = []
        for name, meta in store.items():
            entries.append(CredentialEntry(
                name=name,
                provider=meta.get("provider", "unknown"),
                key_hint=meta.get("hint", "????"),
                source=meta.get("source", "file"),
                created_at=meta.get("created_at", ""),
            ))
        return entries

    def get(self, name: str) -> Optional[str]:
        """Retrieve a credential value. Returns None if not found."""
        # 1. Try keyring
        if self._keyring_available:
            try:
                import keyring
                value = keyring.get_password(self.KEYRING_SERVICE, name)
                if value is not None:
                    return value
            except Exception as e:
                logger.debug(f"[VECTOR][auth] Keyring get error: {e}")

        # 2. Try file store
        store = self._load_file_store()
        entry = store.get(name)
        if entry and "_obfuscated" in entry:
            try:
                return _xor_deobfuscate(entry["_obfuscated"]).decode("utf-8")
            except Exception as e:
                logger.warning(f"[VECTOR][auth] Could not deobfuscate '{name}': {e}")
                return None

        return None

    def test(self, name: str) -> dict:
        """
        Test a credential by making a minimal API call.
        Returns {"name": name, "provider": ..., "valid": bool, "latency_ms": N}
        """
        import time

        store = self._load_file_store()
        meta = store.get(name)
        if not meta:
            return {"name": name, "valid": False, "error": "Credential not found"}

        provider = meta.get("provider", "").lower()
        key = self.get(name)
        if key is None:
            return {"name": name, "provider": provider, "valid": False, "error": "Could not retrieve key"}

        cfg = _PROVIDER_TEST.get(provider)
        if provider == "freellmapi":
            # Configurable endpoint: validated per call; diagnostics never carry the URL or key.
            try:
                from vectorcode.src.providers.coding_catalog import get_coding_provider

                cfg = {
                    "url": get_coding_provider(provider).base_url + "/models",
                    "headers_fn": lambda k: {"Authorization": f"Bearer {k}"},
                    "method": "GET",
                }
            except ValueError:
                return {"name": name, "provider": provider, "valid": False,
                        "error": "FreeLLMAPI endpoint configuration is invalid"}
        if not cfg:
            return {
                "name": name,
                "provider": provider,
                "valid": None,
                "error": f"No test endpoint configured for provider '{provider}'",
            }

        try:
            import httpx
        except ImportError:
            return {"name": name, "provider": provider, "valid": False, "error": "httpx not installed"}

        headers = cfg["headers_fn"](key)
        params = cfg.get("params_fn", lambda k: {})(key)
        url = cfg["url"]

        t0 = time.monotonic()
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.request(cfg["method"], url, headers=headers, params=params)
            latency_ms = round((time.monotonic() - t0) * 1000)
            valid = resp.status_code in (200, 201, 206)
            return {
                "name": name,
                "provider": provider,
                "valid": valid,
                "latency_ms": latency_ms,
                "status_code": resp.status_code,
            }
        except Exception as e:
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "name": name,
                "provider": provider,
                "valid": False,
                "latency_ms": latency_ms,
                "error": type(e).__name__ if provider == "freellmapi" else str(e),
            }

    def from_env(self) -> list[CredentialEntry]:
        """
        Scan environment variables for known API key patterns and register them.
        Returns the list of newly registered credentials.
        """
        import os
        registered: list[CredentialEntry] = []
        for env_var, provider in _ENV_PATTERNS.items():
            value = os.environ.get(env_var)
            if not value:
                continue
            # Derive a stable name from the env var
            cred_name = f"{provider}-env"
            result = self.add(cred_name, provider, value)
            store = self._load_file_store()
            meta = store.get(cred_name, {})
            registered.append(CredentialEntry(
                name=cred_name,
                provider=provider,
                key_hint=meta.get("hint", value[-4:]),
                source="env",
                created_at=meta.get("created_at", ""),
            ))
            logger.info(f"[VECTOR][auth] Imported {env_var} → '{cred_name}'")
        return registered

def get_auth_manager() -> "AuthManager":
    """Return singleton AuthManager."""
    global _auth_manager_instance
    if _auth_manager_instance is None:
        _auth_manager_instance = AuthManager()
    return _auth_manager_instance

# ── CLI helpers ──────────────────────────────────────────────────────────────

def _print_credentials_table(entries: list[CredentialEntry]) -> None:
    if not entries:
        print("No credentials stored.")
        return
    print(f"{'Name':<28}  {'Provider':<14}  {'Hint':<6}  {'Source':<8}  Created")
    print("-" * 80)
    for e in entries:
        ts = e.created_at[:19] if e.created_at else ""
        print(f"  {e.name:<26}  {e.provider:<14}  ...{e.key_hint:<4}  {e.source:<8}  {ts}")

def handle_auth(args) -> None:
    """Dispatch auth subcommands from argparse args."""
    try:
        _handle_auth(args)
    except CredentialStoreCorruptedError as e:
        print(f"[VECTOR] {e}")
        print(f"[VECTOR] Inspect or restore {AuthManager.STORAGE_PATH} manually before retrying.")


def _handle_auth(args) -> None:
    mgr = get_auth_manager()
    action = getattr(args, "auth_action", None)

    if action == "add":
        name = args.name
        provider = args.provider
        key = getattr(args, "key", None) or ""
        if not key:
            try:
                key = getpass.getpass(f"API key for '{name}' ({provider}): ")
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return
        if not key.strip():
            print("[VECTOR] No key provided — aborted.")
            return
        result = mgr.add(name, provider, key.strip())
        print(f"Stored '{result['name']}' ({result['provider']}) in {result['stored']}.")

    elif action == "list":
        entries = mgr.list_credentials()
        _print_credentials_table(entries)

    elif action == "remove":
        result = mgr.remove(args.name)
        if result.get("removed"):
            print(f"Removed '{args.name}' from: {', '.join(result.get('sources', []))}.")
        else:
            print(f"[VECTOR] {result.get('error', 'Remove failed')}")

    elif action == "test":
        result = mgr.test(args.name)
        valid_str = "VALID" if result.get("valid") else "INVALID"
        latency = result.get("latency_ms", -1)
        error = result.get("error", "")
        if result.get("valid") is None:
            print(f"  {args.name}: {error}")
        elif result.get("valid"):
            print(f"  ✓ {args.name} ({result.get('provider', '?')}) — {valid_str}  {latency}ms")
        else:
            err_suffix = f"  error: {error}" if error else ""
            print(f"  ✗ {args.name} ({result.get('provider', '?')}) — {valid_str}  {latency}ms{err_suffix}")

    elif action == "from-env":
        entries = mgr.from_env()
        if not entries:
            print("No known API key environment variables found.")
        else:
            print(f"Imported {len(entries)} credential(s):")
            _print_credentials_table(entries)

    else:
        print("Usage: vector auth <add|list|remove|test|from-env>")

# ── Smoke test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mgr = get_auth_manager()

    # list_credentials returns empty list on fresh install
    creds = mgr.list_credentials()
    assert isinstance(creds, list), "list_credentials must return a list"

    # add + get + remove round-trip (uses file store to avoid keyring dependency)
    test_key = "sk-test-1234567890abcdef"
    mgr._keyring_available = False  # force file store for deterministic test
    result = mgr.add("_smoke_test", "openai", test_key)
    assert result["name"] == "_smoke_test"
    assert result["stored"] == "file"

    retrieved = mgr.get("_smoke_test")
    assert retrieved == test_key, f"Expected {test_key!r}, got {retrieved!r}"

    rm_result = mgr.remove("_smoke_test")
    assert rm_result["removed"] is True

    gone = mgr.get("_smoke_test")
    assert gone is None

    print("✅ cli/auth.py OK")
