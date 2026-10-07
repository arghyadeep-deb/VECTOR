"""VectorCode credential pool — multi-key failover with cooldown persistence.

Ported from reference agent/credential_pool.py, adapted for VectorCode's
provider config (TOML-based, no OAuth, API-key only).

Pool strategy uses: fill_first (default) or round_robin.
Cooldown status is persisted to ~/.vector/credentials_status.json so that
exhausted keys survive process restarts.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional


try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

from loguru import logger
from vectorcode.src.utils import atomic_json_write

# ── Paths ─────────────────────────────────────────────────────────────────────
_VECTOR_DATA_DIR   = Path.home() / ".vector"
_STATUS_FILE       = _VECTOR_DATA_DIR / "credentials_status.json"

# ── Constants ─────────────────────────────────────────────────────────────────
STATUS_OK         = "ok"
STATUS_EXHAUSTED  = "exhausted"
STATUS_ERROR      = "error"

STRATEGY_FILL_FIRST  = "fill_first"
STRATEGY_ROUND_ROBIN = "round_robin"

DEFAULT_COOLDOWN_SECONDS = 60.0


# ── PooledCredential ──────────────────────────────────────────────────────────

@dataclass
class PooledCredential:
    """A single API key entry inside a CredentialPool."""

    provider: str
    id: str
    label: str
    source: str         # env:VAR_NAME | config:name | file:path
    api_key: str
    base_url: str = ""
    priority: int = 0

    # Status tracking — persisted across restarts
    status: str = STATUS_OK
    status_at: float = 0.0
    error_code: Optional[int] = None
    cooldown_until: float = 0.0   # epoch seconds

    request_count: int = 0

    @property
    def is_available(self) -> bool:
        """True when not exhausted or when the cooldown has elapsed."""
        if self.status == STATUS_OK:
            return True
        return time.time() > self.cooldown_until

    @classmethod
    def from_env(cls, provider: str, var_name: str) -> "Optional[PooledCredential]":
        """Read an API key through VECTOR's keyring-first secret manager."""
        from core.security.secrets_manager import get_secret

        api_key = get_secret(var_name).strip()
        if not api_key:
            return None
        return cls(
            provider=provider,
            id=uuid.uuid4().hex[:8],
            label=var_name,
            source=f"env:{var_name}",
            api_key=api_key,
        )

    @classmethod
    def from_config(
        cls,
        provider: str,
        label: str,
        api_key: str,
        base_url: str = "",
    ) -> "PooledCredential":
        """Create a credential from inline config values."""
        return cls(
            provider=provider,
            id=uuid.uuid4().hex[:8],
            label=label,
            source=f"config:{label}",
            api_key=api_key,
            base_url=base_url,
        )

    def to_status_dict(self) -> dict:
        """Serialisable subset used for cooldown persistence."""
        return {
            "status":        self.status,
            "status_at":     self.status_at,
            "error_code":    self.error_code,
            "cooldown_until": self.cooldown_until,
            "request_count": self.request_count,
        }

    def apply_status_dict(self, d: dict) -> None:
        """Restore persisted status fields."""
        self.status         = d.get("status", STATUS_OK)
        self.status_at      = float(d.get("status_at", 0.0))
        self.error_code     = d.get("error_code")
        self.cooldown_until = float(d.get("cooldown_until", 0.0))
        self.request_count  = int(d.get("request_count", 0))


# ── CredentialPool ────────────────────────────────────────────────────────────

class CredentialPool:
    """Manages a set of credentials for one provider."""

    def __init__(
        self,
        provider: str,
        entries: List[PooledCredential],
        strategy: str = STRATEGY_FILL_FIRST,
    ) -> None:
        self.provider  = provider
        self._strategy = strategy
        self._lock     = threading.Lock()
        # Sort by priority ascending (lowest priority number = preferred)
        self._entries: List[PooledCredential] = sorted(
            entries, key=lambda e: e.priority
        )
        self._rr_index = 0   # round-robin cursor

    # ── Selection ─────────────────────────────────────────────────────────────

    def select(self) -> Optional[PooledCredential]:
        """Return the best available credential according to strategy."""
        with self._lock:
            available = [e for e in self._entries if e.is_available]
            if not available:
                logger.warning(
                    f"[VECTOR][creds] pool '{self.provider}': all credentials exhausted"
                )
                return None

            if self._strategy == STRATEGY_ROUND_ROBIN:
                idx = self._rr_index % len(available)
                chosen = available[idx]
                self._rr_index = (idx + 1) % len(available)
            else:
                # fill_first — always pick the highest-priority available entry
                chosen = available[0]

            chosen.request_count += 1
            return chosen

    # ── Status mutations ──────────────────────────────────────────────────────

    def mark_exhausted(
        self,
        credential_id: str,
        status_code: int,
        retry_after_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ) -> Optional[PooledCredential]:
        """Mark a credential exhausted with cooldown. Returns next available."""
        with self._lock:
            entry = self._by_id(credential_id)
            if entry is None:
                logger.warning(
                    f"[VECTOR][creds] mark_exhausted: unknown id {credential_id!r}"
                )
                return None
            entry.status         = STATUS_EXHAUSTED
            entry.status_at      = time.time()
            entry.error_code     = status_code
            entry.cooldown_until = time.time() + retry_after_seconds
            logger.info(
                f"[VECTOR][creds] {self.provider}/{entry.label} exhausted "
                f"(HTTP {status_code}), cooldown {retry_after_seconds:.0f}s"
            )
        self._persist_status()
        # Re-select to get the next available
        return self.select()

    def mark_error(self, credential_id: str, error_code: int) -> None:
        """Mark a credential as errored (permanent until manual reset)."""
        with self._lock:
            entry = self._by_id(credential_id)
            if entry is None:
                return
            entry.status     = STATUS_ERROR
            entry.status_at  = time.time()
            entry.error_code = error_code
            logger.error(
                f"[VECTOR][creds] {self.provider}/{entry.label} auth error "
                f"(code {error_code}) — marking permanent error"
            )
        self._persist_status()

    def reset_all(self) -> int:
        """Clear all exhaustion/error status. Returns count reset."""
        count = 0
        with self._lock:
            for entry in self._entries:
                if entry.status != STATUS_OK:
                    entry.status         = STATUS_OK
                    entry.status_at      = 0.0
                    entry.error_code     = None
                    entry.cooldown_until = 0.0
                    count += 1
        if count:
            self._persist_status()
        return count

    # ── Mutation ──────────────────────────────────────────────────────────────

    def add(self, cred: PooledCredential) -> None:
        """Append a credential to the pool."""
        with self._lock:
            cred.priority = max((e.priority for e in self._entries), default=-1) + 1
            self._entries.append(cred)
        self._persist_status()

    def has_available(self) -> bool:
        """Return True if at least one credential is not in cooldown."""
        with self._lock:
            return any(e.is_available for e in self._entries)

    def entries(self) -> list:
        """Return all entries (snapshot)."""
        with self._lock:
            return list(self._entries)

    def rotate(self) -> None:
        """Mark the current credential exhausted and advance to the next.
        Called by engine/recovery.py on 429/401 errors.
        """
        with self._lock:
            available = [e for e in self._entries if e.is_available]
            if not available:
                return
            # Mark the first available as exhausted temporarily
            current = available[0]
            current.status = STATUS_EXHAUSTED
            current.cooldown_until = time.time() + DEFAULT_COOLDOWN_SECONDS
            current.status_at = time.time()
        self._persist_status()
        logger.info(f"[VECTOR][creds] rotated away from {current.label!r}")

    def list_all(self) -> List[PooledCredential]:
        """Return a snapshot of all entries."""
        with self._lock:
            return list(self._entries)

    def get(self, credential_id: str) -> Optional[PooledCredential]:
        """Return the entry with the given id, or None."""
        with self._lock:
            return self._by_id(credential_id)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _by_id(self, credential_id: str) -> Optional[PooledCredential]:
        """Find entry by id (caller must hold lock)."""
        for e in self._entries:
            if e.id == credential_id:
                return e
        return None

    def _persist_status(self) -> None:
        """Write cooldown status for all entries to disk (best-effort)."""
        try:
            _VECTOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                entries_snapshot = list(self._entries)
            # Merge with existing file so other providers are preserved
            existing: dict = {}
            if _STATUS_FILE.exists():
                try:
                    existing = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            pool_status: dict = existing.get(self.provider, {})
            for entry in entries_snapshot:
                pool_status[entry.id] = entry.to_status_dict()
            existing[self.provider] = pool_status
            atomic_json_write(_STATUS_FILE, existing)
        except Exception as exc:
            logger.debug(f"[VECTOR][creds] failed to persist status: {exc}")

    def _restore_status(self) -> None:
        """Load persisted cooldown status from disk (best-effort)."""
        if not _STATUS_FILE.exists():
            return
        try:
            data = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
            pool_data: dict = data.get(self.provider, {})
            with self._lock:
                for entry in self._entries:
                    if entry.id in pool_data:
                        entry.apply_status_dict(pool_data[entry.id])
        except Exception as exc:
            logger.debug(f"[VECTOR][creds] failed to restore status: {exc}")


# ── CredentialManager ─────────────────────────────────────────────────────────

class CredentialManager:
    """Singleton manager for all provider credential pools."""

    _instance: "Optional[CredentialManager]" = None
    _init_lock = threading.Lock()

    @classmethod
    def get(cls) -> "CredentialManager":
        """Return the singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._pools: Dict[str, CredentialPool] = {}
        self._lock  = threading.Lock()

    def load_from_config(self, config: dict) -> None:
        """Build credential pools from VectorConfig providers dict.

        Supports:
          providers.<name>.api_key          — single inline key
          providers.<name>.api_keys         — list of inline keys
          providers.<name>.api_key_env      — env var name
          providers.<name>.base_url         — optional base URL
        """
        providers = config.get("providers", {})
        if not isinstance(providers, dict):
            return

        for provider_name, prov_cfg in providers.items():
            if not isinstance(prov_cfg, dict):
                continue
            entries: List[PooledCredential] = []
            base_url = prov_cfg.get("base_url", "")

            # 1. env var
            env_var = prov_cfg.get("api_key_env", "")
            if env_var:
                cred = PooledCredential.from_env(provider_name, env_var)
                if cred:
                    cred.base_url = base_url
                    entries.append(cred)

            # 2. single inline api_key
            single_key = (prov_cfg.get("api_key") or "").strip()
            if single_key:
                entries.append(
                    PooledCredential.from_config(
                        provider_name, f"{provider_name}-key", single_key, base_url
                    )
                )

            # 3. list of keys
            key_list = prov_cfg.get("api_keys", [])
            if isinstance(key_list, list):
                for idx, key in enumerate(key_list):
                    if isinstance(key, str) and key.strip():
                        entries.append(
                            PooledCredential.from_config(
                                provider_name,
                                f"{provider_name}-key{idx}",
                                key.strip(),
                                base_url,
                            )
                        )

            if not entries:
                continue

            strategy = prov_cfg.get("pool_strategy", STRATEGY_FILL_FIRST)
            pool = CredentialPool(provider_name, entries, strategy=strategy)
            pool._restore_status()

            with self._lock:
                self._pools[provider_name] = pool

            logger.info(
                f"[VECTOR][creds] provider '{provider_name}': "
                f"{len(entries)} credential(s) loaded"
            )

    def get_pool(self, provider: str) -> Optional[CredentialPool]:
        """Return the pool for a provider, or None."""
        with self._lock:
            return self._pools.get(provider)

    def select(self, provider: str) -> Optional[PooledCredential]:
        """Select the best credential for a provider."""
        pool = self.get_pool(provider)
        if pool is None:
            logger.warning(
                f"[VECTOR][creds] no pool for provider '{provider}'"
            )
            return None
        return pool.select()

    def on_rate_limit(
        self,
        provider: str,
        credential_id: str,
        retry_after: float = DEFAULT_COOLDOWN_SECONDS,
    ) -> Optional[PooledCredential]:
        """Mark a credential exhausted (rate-limit), rotate to next."""
        pool = self.get_pool(provider)
        if pool is None:
            return None
        return pool.mark_exhausted(credential_id, 429, retry_after)

    def on_auth_error(
        self, provider: str, credential_id: str
    ) -> Optional[PooledCredential]:
        """Mark a credential as permanently errored, try to return next."""
        pool = self.get_pool(provider)
        if pool is None:
            return None
        pool.mark_error(credential_id, 401)
        return pool.select()

    def status_report(self) -> str:
        """Human-readable status of all pools."""
        lines: List[str] = ["Credential Pool Status:"]
        with self._lock:
            pools_snapshot = dict(self._pools)

        if not pools_snapshot:
            return "  (no pools loaded)"

        for provider, pool in sorted(pools_snapshot.items()):
            entries = pool.list_all()
            available = sum(1 for e in entries if e.is_available)
            lines.append(
                f"  {provider}: {available}/{len(entries)} available "
                f"[strategy: {pool._strategy}]"
            )
            for e in entries:
                if e.status == STATUS_OK:
                    tag = "ok"
                elif e.status == STATUS_EXHAUSTED:
                    remaining = max(0.0, e.cooldown_until - time.time())
                    tag = f"cooldown {remaining:.0f}s"
                else:
                    tag = f"error({e.error_code})"
                lines.append(
                    f"    [{tag}] {e.label} (req={e.request_count})"
                )
        return "\n".join(lines)


# ── Module-level convenience ──────────────────────────────────────────────────

def get_credential_manager() -> CredentialManager:
    """Return the singleton CredentialManager, loading config on first call."""
    mgr = CredentialManager.get()
    if not mgr._pools:
        try:
            from config import VectorConfig
            cfg = VectorConfig()
            mgr.load_from_config(cfg._cfg)
        except Exception as exc:
            logger.debug(f"[VECTOR][creds] config load skipped: {exc}")
    return mgr


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    # --- PooledCredential ---
    cred = PooledCredential.from_config("anthropic", "test-key", "sk-ant-test-1234")
    assert cred.provider == "anthropic"
    assert cred.api_key == "sk-ant-test-1234"
    assert cred.is_available is True

    # from_env with a real env var
    os.environ["_VECTOR_TEST_KEY"] = "sk-test-env-9999"
    env_cred = PooledCredential.from_env("openai", "_VECTOR_TEST_KEY")
    assert env_cred is not None
    assert env_cred.api_key == "sk-test-env-9999"
    assert env_cred.source == "env:_VECTOR_TEST_KEY"

    # from_env returns None for missing var
    none_cred = PooledCredential.from_env("openai", "_VECTOR_MISSING_KEY_XYZ")
    assert none_cred is None

    # --- CredentialPool ---
    entries = [
        PooledCredential.from_config("test-prov", "key-a", "key-aaa"),
        PooledCredential.from_config("test-prov", "key-b", "key-bbb"),
    ]
    pool = CredentialPool("test-prov", entries)
    selected = pool.select()
    assert selected is not None
    assert selected.api_key == "key-aaa"   # fill_first picks priority 0
    assert selected.request_count == 1

    # Exhaust first key
    next_cred = pool.mark_exhausted(selected.id, 429, retry_after_seconds=3600.0)
    assert next_cred is not None
    assert next_cred.api_key == "key-bbb"

    # Reset
    reset_count = pool.reset_all()
    assert reset_count >= 1
    after_reset = pool.select()
    assert after_reset.api_key == "key-aaa"  # back to fill_first priority

    # Round-robin
    rr_pool = CredentialPool("rr-prov", [
        PooledCredential.from_config("rr-prov", "rr-a", "rrkey-a"),
        PooledCredential.from_config("rr-prov", "rr-b", "rrkey-b"),
    ], strategy=STRATEGY_ROUND_ROBIN)
    first  = rr_pool.select()
    second = rr_pool.select()
    assert first.id != second.id or len(rr_pool.list_all()) == 1

    # --- CredentialManager ---
    # Reset singleton for test isolation
    CredentialManager._instance = None
    mgr = CredentialManager.get()
    os.environ["_VECTOR_CRED_TEST_ANTHROPIC"] = "sk-ant-manager-test"
    mgr.load_from_config({
        "providers": {
            "anthropic": {
                "api_key_env": "_VECTOR_CRED_TEST_ANTHROPIC",
                "base_url": "https://api.anthropic.com",
            },
            "local-ollama": {
                "base_url": "http://localhost:11434",
            },
        }
    })
    assert mgr.get_pool("anthropic") is not None
    cred_selected = mgr.select("anthropic")
    assert cred_selected is not None
    assert cred_selected.api_key == "sk-ant-manager-test"

    # Provider with no keys — pool not created
    assert mgr.get_pool("local-ollama") is None

    # on_rate_limit
    next_after_rl = mgr.on_rate_limit("anthropic", cred_selected.id, retry_after=5.0)
    # Only one key — None expected
    assert next_after_rl is None

    # Status report
    report = mgr.status_report()
    assert "anthropic" in report

    print("credentials.py OK")


