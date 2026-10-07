"""Credential sources — registry for removing credentials from 9 external locations.

Used by `vector auth remove <name>` to clean up credentials from every possible
location where a credential might have been stored.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


try:
    from core.config import CONFIG  # noqa: F401
except ImportError:
    CONFIG = {}

from loguru import logger


# ── Enums & Dataclasses ───────────────────────────────────────────────────────

class CredentialSource(str, Enum):
    ENV      = "env"          # environment variable
    PKCE     = "pkce"         # OAuth PKCE token file  (~/.vector/oauth_tokens.json)
    CLAUDE   = "claude_code"  # ~/.claude/credentials.json
    NOUS     = "nous"         # VectorCode config file  (~/.vectorcode/config.json)
    CODEX    = "codex"        # OpenAI Codex config (~/.openai/credentials)
    QWEN     = "qwen"         # Qwen config         (~/.qwen/config.json)
    COPILOT  = "copilot"      # GitHub Copilot token (~/.config/github-copilot/hosts.json)
    CONFIG   = "config"       # ~/.vector/config.json
    KEYRING  = "keyring"      # system keyring


@dataclass
class RemovalResult:
    source: CredentialSource
    cleaned: bool            # True if something was actually removed
    hints: list[str]         # Human-readable hints for what was done
    suppress: bool = False   # If True, block re-seeding from this source


@dataclass
class RemovalStep:
    source: CredentialSource
    description: str
    execute: Callable[[], RemovalResult]


# ── Atomic JSON helpers ───────────────────────────────────────────────────────

def atomic_json_write(path: Path, data: dict) -> None:
    """Write JSON atomically using a temp file + os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception as _sve:
        # If temp write failed, clean up leftover .tmp
        try:
            tmp.unlink(missing_ok=True)
        except Exception as _sve:
            logger.debug("[VECTOR][credential_sources] suppressed Exception: %s", _sve)
        raise


def _pop_key_from_dict(data: dict, credential_name: str) -> tuple[dict, bool]:
    """
    Recursively remove *credential_name* from a nested dict.
    Returns (modified_dict, was_modified).
    Checks both top-level keys and common credential container keys
    ("credentials", "tokens", "keys").
    """
    CONTAINER_KEYS = {"credentials", "tokens", "keys", "api_keys"}
    removed = False

    # direct top-level removal
    if credential_name in data:
        del data[credential_name]
        removed = True

    # search inside known container keys
    for container in CONTAINER_KEYS:
        if container in data and isinstance(data[container], dict):
            if credential_name in data[container]:
                del data[container][credential_name]
                removed = True

    return data, removed


# ── Registry ──────────────────────────────────────────────────────────────────

class CredentialSourceRegistry:
    """
    Registry of removal steps for each credential source.
    Used by `vector auth remove <name>` to clean up credentials everywhere.
    """

    def __init__(self) -> None:
        self._steps: dict[CredentialSource, RemovalStep] = {}
        self._suppressed: set[CredentialSource] = set()
        self._current_name: str = ""   # set during execute_removal()
        self._register_all()

    # ── Registration ──────────────────────────────────────────────────────────

    def _register_all(self) -> None:
        """Register removal steps for all 9 sources."""

        self._steps[CredentialSource.KEYRING] = RemovalStep(
            source=CredentialSource.KEYRING,
            description="Remove from system keyring",
            execute=self._remove_keyring,
        )
        self._steps[CredentialSource.CONFIG] = RemovalStep(
            source=CredentialSource.CONFIG,
            description="Remove from ~/.vector/config.json",
            execute=self._remove_config,
        )
        self._steps[CredentialSource.ENV] = RemovalStep(
            source=CredentialSource.ENV,
            description="Scan environment variables for key",
            execute=self._remove_env,
        )
        self._steps[CredentialSource.CLAUDE] = RemovalStep(
            source=CredentialSource.CLAUDE,
            description="Remove from ~/.claude/credentials.json",
            execute=self._remove_claude,
        )
        self._steps[CredentialSource.PKCE] = RemovalStep(
            source=CredentialSource.PKCE,
            description="Remove OAuth PKCE token from ~/.vector/oauth_tokens.json",
            execute=self._remove_pkce,
        )
        self._steps[CredentialSource.NOUS] = RemovalStep(
            source=CredentialSource.NOUS,
            description="Remove from VectorCode config (~/.vectorcode/config.json)",
            execute=self._remove_nous,
        )
        self._steps[CredentialSource.CODEX] = RemovalStep(
            source=CredentialSource.CODEX,
            description="Remove from OpenAI Codex config (~/.openai/credentials)",
            execute=self._remove_codex,
        )
        self._steps[CredentialSource.QWEN] = RemovalStep(
            source=CredentialSource.QWEN,
            description="Remove from Qwen config (~/.qwen/config.json)",
            execute=self._remove_qwen,
        )
        self._steps[CredentialSource.COPILOT] = RemovalStep(
            source=CredentialSource.COPILOT,
            description="Remove from GitHub Copilot hosts (~/.config/github-copilot/hosts.json)",
            execute=self._remove_copilot,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def execute_removal(self, credential_name: str) -> list[RemovalResult]:
        """
        Execute all registered removal steps for *credential_name*.
        Skip suppressed sources.
        Returns list of RemovalResult — one per source attempted.
        """
        self._current_name = credential_name
        results: list[RemovalResult] = []

        for source, step in self._steps.items():
            if source in self._suppressed:
                logger.debug(
                    f"[VECTOR][cred_sources] skipping suppressed source: {source.value}"
                )
                continue
            try:
                result = step.execute()
                if result.cleaned:
                    logger.info(
                        f"[VECTOR][cred_sources] removed '{credential_name}' "
                        f"from {source.value}"
                    )
                else:
                    logger.debug(
                        f"[VECTOR][cred_sources] {source.value}: nothing removed "
                        f"for '{credential_name}'"
                    )
                if result.suppress:
                    self._suppressed.add(source)
                results.append(result)
            except Exception as exc:
                logger.warning(
                    f"[VECTOR][cred_sources] {source.value} removal step raised: {exc}"
                )
                results.append(
                    RemovalResult(
                        source=source,
                        cleaned=False,
                        hints=[f"Step raised exception: {exc}"],
                    )
                )

        self._current_name = ""
        return results

    def suppress_source(self, source: CredentialSource) -> None:
        """Block re-seeding from this source after removal."""
        self._suppressed.add(source)
        logger.debug(f"[VECTOR][cred_sources] suppressed: {source.value}")

    def is_suppressed(self, source: CredentialSource) -> bool:
        """Check if source is suppressed."""
        return source in self._suppressed

    def list_steps(self) -> list[dict]:
        """List all registered removal steps as plain dicts."""
        return [
            {
                "source": step.source.value,
                "description": step.description,
                "suppressed": step.source in self._suppressed,
            }
            for step in self._steps.values()
        ]

    # ── Private removal implementations ───────────────────────────────────────

    def _remove_keyring(self) -> RemovalResult:
        """Try keyring.delete_password(). Return cleaned=True if the entry existed."""
        name = self._current_name
        try:
            import keyring  # type: ignore[import]
            service = "vectorcode"
            existing = keyring.get_password(service, name)
            if existing is not None:
                keyring.delete_password(service, name)
                return RemovalResult(
                    source=CredentialSource.KEYRING,
                    cleaned=True,
                    hints=[f"Deleted keyring entry: service=vectorcode, username={name!r}"],
                )
            return RemovalResult(
                source=CredentialSource.KEYRING,
                cleaned=False,
                hints=[f"No keyring entry found for service='vectorcode', username={name!r}"],
            )
        except ImportError:
            return RemovalResult(
                source=CredentialSource.KEYRING,
                cleaned=False,
                hints=[
                    "keyring not installed — skipped.",
                    f"If installed manually: keyring delete vectorcode {name!r}",
                ],
            )
        except Exception as exc:
            return RemovalResult(
                source=CredentialSource.KEYRING,
                cleaned=False,
                hints=[f"keyring error: {exc}"],
            )

    def _remove_config(self) -> RemovalResult:
        """Remove *credential_name* from ~/.vector/config.json credentials section."""
        name = self._current_name
        config_path = Path.home() / ".vector" / "config.json"
        if not config_path.exists():
            return RemovalResult(
                source=CredentialSource.CONFIG,
                cleaned=False,
                hints=["~/.vector/config.json does not exist — skipped."],
            )
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            data, removed = _pop_key_from_dict(data, name)
            if removed:
                atomic_json_write(config_path, data)
                return RemovalResult(
                    source=CredentialSource.CONFIG,
                    cleaned=True,
                    hints=[f"Removed '{name}' from {config_path}"],
                )
            return RemovalResult(
                source=CredentialSource.CONFIG,
                cleaned=False,
                hints=[f"'{name}' not found in {config_path}"],
            )
        except Exception as exc:
            return RemovalResult(
                source=CredentialSource.CONFIG,
                cleaned=False,
                hints=[f"Error updating {config_path}: {exc}"],
            )

    def _remove_env(self) -> RemovalResult:
        """Check if the credential name appears in env vars — can't remove, but warns."""
        name = self._current_name
        # Look for env vars whose name or value appears to relate to this credential
        upper_name = name.upper().replace("-", "_")
        candidates = [
            k for k in os.environ
            if upper_name in k.upper()
            or k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN",
                     "QWEN_API_KEY", "VECTOR_API_KEY", "CODEX_API_KEY",
                     "COPILOT_TOKEN", "VECTORCODE_API_KEY")
        ]
        if candidates:
            unset_hints = [f"  unset {k}" for k in candidates[:5]]
            return RemovalResult(
                source=CredentialSource.ENV,
                cleaned=False,
                hints=[
                    "Cannot remove env vars programmatically. Remove from your shell rc file:",
                    *unset_hints,
                    "Then restart your shell.",
                ],
                suppress=True,
            )
        return RemovalResult(
            source=CredentialSource.ENV,
            cleaned=True,
            hints=[f"No env var matching '{name}' found in current environment."],
        )

    def _remove_claude(self) -> RemovalResult:
        """Remove *credential_name* from ~/.claude/credentials.json."""
        name = self._current_name
        creds_path = Path.home() / ".claude" / "credentials.json"
        if not creds_path.exists():
            return RemovalResult(
                source=CredentialSource.CLAUDE,
                cleaned=False,
                hints=["~/.claude/credentials.json not found — skipped."],
            )
        try:
            data = json.loads(creds_path.read_text(encoding="utf-8"))
            data, removed = _pop_key_from_dict(data, name)
            if removed:
                atomic_json_write(creds_path, data)
                return RemovalResult(
                    source=CredentialSource.CLAUDE,
                    cleaned=True,
                    hints=[f"Removed '{name}' from {creds_path}"],
                )
            return RemovalResult(
                source=CredentialSource.CLAUDE,
                cleaned=False,
                hints=[
                    f"'{name}' not found in {creds_path}.",
                    f"Inspect manually: {creds_path}",
                ],
            )
        except Exception as exc:
            return RemovalResult(
                source=CredentialSource.CLAUDE,
                cleaned=False,
                hints=[f"Error reading {creds_path}: {exc}"],
            )

    def _remove_pkce(self) -> RemovalResult:
        """Remove OAuth PKCE token for *credential_name* from ~/.vector/oauth_tokens.json."""
        name = self._current_name
        tokens_path = Path.home() / ".vector" / "oauth_tokens.json"
        if not tokens_path.exists():
            return RemovalResult(
                source=CredentialSource.PKCE,
                cleaned=False,
                hints=["~/.vector/oauth_tokens.json does not exist — skipped."],
            )
        try:
            data = json.loads(tokens_path.read_text(encoding="utf-8"))
            data, removed = _pop_key_from_dict(data, name)
            if removed:
                atomic_json_write(tokens_path, data)
                return RemovalResult(
                    source=CredentialSource.PKCE,
                    cleaned=True,
                    hints=[f"Removed PKCE token '{name}' from {tokens_path}"],
                )
            return RemovalResult(
                source=CredentialSource.PKCE,
                cleaned=False,
                hints=[f"PKCE token '{name}' not found in {tokens_path}"],
            )
        except Exception as exc:
            return RemovalResult(
                source=CredentialSource.PKCE,
                cleaned=False,
                hints=[f"Error reading {tokens_path}: {exc}"],
            )

    def _remove_nous(self) -> RemovalResult:
        """Remove *credential_name* from VectorCode config (~/.vectorcode/config.json)."""
        name = self._current_name
        config_path = Path.home() / ".vector" / "config.json"
        if not config_path.exists():
            return RemovalResult(
                source=CredentialSource.NOUS,
                cleaned=False,
                hints=["~/.vectorcode/config.json does not exist — skipped."],
            )
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            removed = False

            # VectorCode stores credentials under "api_key" at top level or in "credentials"
            NOUS_KEY_FIELDS = {"api_key", "token", "secret"}
            for field_name in NOUS_KEY_FIELDS:
                if field_name in data and isinstance(data[field_name], str):
                    # Only remove if the value looks related to the credential name
                    if name.lower() in data[field_name].lower() or name == field_name:
                        del data[field_name]
                        removed = True

            data, also_removed = _pop_key_from_dict(data, name)
            removed = removed or also_removed

            if removed:
                atomic_json_write(config_path, data)
                return RemovalResult(
                    source=CredentialSource.NOUS,
                    cleaned=True,
                    hints=[f"Removed '{name}' from {config_path}"],
                )
            return RemovalResult(
                source=CredentialSource.NOUS,
                cleaned=False,
                hints=[f"'{name}' not found in {config_path}"],
            )
        except Exception as exc:
            return RemovalResult(
                source=CredentialSource.NOUS,
                cleaned=False,
                hints=[f"Error reading {config_path}: {exc}"],
            )

    def _remove_codex(self) -> RemovalResult:
        """Remove *credential_name* from OpenAI Codex config (~/.openai/credentials)."""
        name = self._current_name
        # Codex may use either a JSON credentials file or a plain text file
        json_path = Path.home() / ".openai" / "credentials"
        alt_path  = Path.home() / ".openai" / "credentials.json"

        for creds_path in (json_path, alt_path):
            if not creds_path.exists():
                continue
            try:
                raw = creds_path.read_text(encoding="utf-8").strip()
                # Try JSON first
                try:
                    data = json.loads(raw)
                    data, removed = _pop_key_from_dict(data, name)
                    if removed:
                        atomic_json_write(creds_path, data)
                        return RemovalResult(
                            source=CredentialSource.CODEX,
                            cleaned=True,
                            hints=[f"Removed '{name}' from {creds_path}"],
                        )
                    return RemovalResult(
                        source=CredentialSource.CODEX,
                        cleaned=False,
                        hints=[f"'{name}' not found in {creds_path}"],
                    )
                except json.JSONDecodeError:
                    # Plain text file — can't safely modify without knowing structure
                    return RemovalResult(
                        source=CredentialSource.CODEX,
                        cleaned=False,
                        hints=[
                            f"Codex credentials file at {creds_path} is not JSON.",
                            f"Inspect and remove '{name}' manually.",
                        ],
                    )
            except Exception as exc:
                return RemovalResult(
                    source=CredentialSource.CODEX,
                    cleaned=False,
                    hints=[f"Error reading {creds_path}: {exc}"],
                )

        return RemovalResult(
            source=CredentialSource.CODEX,
            cleaned=False,
            hints=["~/.openai/credentials (or .json) not found — skipped."],
        )

    def _remove_qwen(self) -> RemovalResult:
        """Remove *credential_name* from Qwen config (~/.qwen/config.json)."""
        name = self._current_name
        config_path = Path.home() / ".qwen" / "config.json"
        if not config_path.exists():
            return RemovalResult(
                source=CredentialSource.QWEN,
                cleaned=False,
                hints=["~/.qwen/config.json does not exist — skipped."],
            )
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            data, removed = _pop_key_from_dict(data, name)
            if removed:
                atomic_json_write(config_path, data)
                return RemovalResult(
                    source=CredentialSource.QWEN,
                    cleaned=True,
                    hints=[f"Removed '{name}' from {config_path}"],
                )
            return RemovalResult(
                source=CredentialSource.QWEN,
                cleaned=False,
                hints=[f"'{name}' not found in {config_path}"],
            )
        except Exception as exc:
            return RemovalResult(
                source=CredentialSource.QWEN,
                cleaned=False,
                hints=[f"Error reading {config_path}: {exc}"],
            )

    def _remove_copilot(self) -> RemovalResult:
        """Remove *credential_name* from GitHub Copilot hosts.json."""
        name = self._current_name
        hosts_path = Path.home() / ".config" / "github-copilot" / "hosts.json"
        if not hosts_path.exists():
            # Try Windows-style path
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                alt = Path(appdata) / "GitHub Copilot" / "hosts.json"
                if alt.exists():
                    hosts_path = alt
                else:
                    return RemovalResult(
                        source=CredentialSource.COPILOT,
                        cleaned=False,
                        hints=["GitHub Copilot hosts.json not found — skipped."],
                    )
            else:
                return RemovalResult(
                    source=CredentialSource.COPILOT,
                    cleaned=False,
                    hints=["~/.config/github-copilot/hosts.json not found — skipped."],
                )
        try:
            data = json.loads(hosts_path.read_text(encoding="utf-8"))
            data, removed = _pop_key_from_dict(data, name)
            if removed:
                atomic_json_write(hosts_path, data)
                return RemovalResult(
                    source=CredentialSource.COPILOT,
                    cleaned=True,
                    hints=[f"Removed '{name}' from {hosts_path}"],
                )
            return RemovalResult(
                source=CredentialSource.COPILOT,
                cleaned=False,
                hints=[f"'{name}' not found in {hosts_path}"],
            )
        except Exception as exc:
            return RemovalResult(
                source=CredentialSource.COPILOT,
                cleaned=False,
                hints=[f"Error reading {hosts_path}: {exc}"],
            )


# ── Singleton factory ─────────────────────────────────────────────────────────

_registry_instance: Optional[CredentialSourceRegistry] = None


def get_credential_source_registry() -> CredentialSourceRegistry:
    """Return the singleton CredentialSourceRegistry."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = CredentialSourceRegistry()
    return _registry_instance


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    # 1. Registry initialises correctly — 9 steps registered
    registry = CredentialSourceRegistry()
    steps = registry.list_steps()
    assert len(steps) == 9, f"Expected 9 steps, got {len(steps)}: {[s['source'] for s in steps]}"
    sources_in_steps = {s["source"] for s in steps}
    for src in CredentialSource:
        assert src.value in sources_in_steps, f"Missing source in registry: {src.value}"
    logger.info("[VECTOR][cred_sources] list_steps() OK — 9 sources registered")

    # 2. Suppress / is_suppressed round-trip
    registry.suppress_source(CredentialSource.ENV)
    assert registry.is_suppressed(CredentialSource.ENV) is True
    assert registry.is_suppressed(CredentialSource.KEYRING) is False
    logger.info("[VECTOR][cred_sources] suppress/is_suppressed OK")

    # 3. execute_removal runs without crashing — returns list of RemovalResults
    fresh = CredentialSourceRegistry()   # unsuppressed
    results = fresh.execute_removal("test-credential")
    assert isinstance(results, list), "execute_removal must return a list"
    # ENV is not suppressed in fresh registry, so we get results for all sources
    # (some suppressed mid-run if ENV suppresses itself, that's fine)
    # At minimum we must get a result per step that was not suppressed at call time
    assert len(results) >= 1, "Must return at least one RemovalResult"
    for r in results:
        assert isinstance(r, RemovalResult), f"Expected RemovalResult, got {type(r)}"
        assert isinstance(r.hints, list), "hints must be a list"
        assert isinstance(r.cleaned, bool), "cleaned must be a bool"
    logger.info(f"[VECTOR][cred_sources] execute_removal OK — {len(results)} results")

    # 4. atomic_json_write round-trip
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = Path(tmpdir) / "test.json"
        test_data = {"key": "value", "nested": {"a": 1}}
        atomic_json_write(test_path, test_data)
        loaded = json.loads(test_path.read_text())
        assert loaded == test_data, "atomic_json_write round-trip mismatch"
    logger.info("[VECTOR][cred_sources] atomic_json_write OK")

    # 5. Singleton returns same instance
    reg_a = get_credential_source_registry()
    reg_b = get_credential_source_registry()
    assert reg_a is reg_b, "get_credential_source_registry must return singleton"
    logger.info("[VECTOR][cred_sources] singleton OK")

    print("credential_sources.py OK")
