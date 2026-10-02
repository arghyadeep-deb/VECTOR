"""Nous Portal upstream adapter.

Reads the user's Nous OAuth state from ``~/.vector/auth.json``, refreshes
the access token and mints a fresh agent key when needed, and exposes the
upstream base URL plus minted bearer for the proxy server to forward to.

The minted ``agent_key`` (not the OAuth ``access_token``) is what
``inference-api.vector.com`` accepts as a bearer. The refresh helper
already handles both — see :func:`vector_cli.auth.refresh_nous_oauth_from_state`.

NOTE (Phase 3 audit, 2026-10-02): _save_state() used to also call
vector_cli.auth._write_shared_nous_state(state) -- that name has never
existed anywhere in auth.py's git history (confirmed), so importing this
module raised ImportError immediately, making the whole adapter
unusable. Zero real callers of VectorPortalAdapter exist anywhere in the
repo (confirmed via grep), so this was never exercised. Removed the
broken import/call; _save_state() already persists via the same
providers.nous + _save_auth_store() path auth.py's own
persist_nous_credentials() uses. If a second, cross-process "shared
state" write was genuinely intended (distinct from the auth store), that
needs a real implementation decided by the owner, not a guess here.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, FrozenSet, Optional

from loguru import logger

from vector_cli.auth import (
    DEFAULT_NOUS_INFERENCE_URL,
    _load_auth_store,
    _save_auth_store,
    refresh_nous_oauth_from_state,
)
from vector_cli.proxy.adapters.base import UpstreamAdapter, UpstreamCredential

# Endpoints inference-api.vector.com actually serves. Anything else
# the proxy will reject with 404 — keeps stray clients from leaking weird
# requests to the upstream.
_ALLOWED_PATHS: FrozenSet[str] = frozenset(
    {
        "/chat/completions",
        "/completions",
        "/embeddings",
        "/models",
    }
)


class VectorPortalAdapter(UpstreamAdapter):
    """Proxy upstream for the Nous Portal inference API."""

    def __init__(self) -> None:
        # Lock guards _load → refresh → _save against parallel proxy requests
        # racing to refresh expired tokens. Refresh itself is HTTP, so we
        # hold the lock across the network call (brief; OAuth refresh is fast).
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "nous"

    @property
    def display_name(self) -> str:
        return "Nous Portal"

    @property
    def allowed_paths(self) -> FrozenSet[str]:
        return _ALLOWED_PATHS

    def is_authenticated(self) -> bool:
        state = self._read_state()
        if state is None:
            return False
        # We need either a usable agent_key OR (refresh_token + access_token)
        # to recover. The refresh helper will mint/refresh as needed.
        return bool(
            state.get("agent_key")
            or (state.get("refresh_token") and state.get("access_token"))
        )

    def get_credential(self) -> UpstreamCredential:
        with self._lock:
            state = self._read_state()
            if state is None:
                raise RuntimeError(
                    "Not logged into Nous Portal. Run `vector login nous` first."
                )

            try:
                refreshed = refresh_nous_oauth_from_state(state)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to refresh Nous Portal credentials: {exc}"
                ) from exc

            self._save_state(refreshed)

            agent_key = refreshed.get("agent_key")
            if not agent_key:
                raise RuntimeError(
                    "Nous Portal refresh did not return a usable agent_key. "
                    "Try `vector login nous` to re-authenticate."
                )

            base_url = refreshed.get("inference_base_url") or DEFAULT_NOUS_INFERENCE_URL
            base_url = base_url.rstrip("/")

            return UpstreamCredential(
                bearer=agent_key,
                base_url=base_url,
                expires_at=refreshed.get("agent_key_expires_at"),
            )

    # ------------------------------------------------------------------
    # Internal helpers — auth.json access. Kept local rather than added
    # to vector_cli.auth to avoid expanding that module's public surface.
    # ------------------------------------------------------------------

    def _read_state(self) -> Optional[Dict[str, Any]]:
        try:
            store = _load_auth_store()
        except Exception as exc:
            logger.warning("proxy: failed to load auth store: {}", exc)
            return None
        providers = store.get("providers") or {}
        state = providers.get("nous")
        if not isinstance(state, dict):
            return None
        return dict(state)  # copy so the refresh helper can mutate freely

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            store = _load_auth_store()
            providers = store.setdefault("providers", {})
            providers["nous"] = state
            _save_auth_store(store)
        except Exception as exc:
            # Best effort — we still return the fresh credential. The next
            # request just won't see cached state, which means another refresh.
            logger.warning("proxy: failed to persist refreshed Nous state: {}", exc)


__all__ = ["VectorPortalAdapter"]
