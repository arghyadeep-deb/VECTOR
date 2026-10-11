# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Google Tasks connector — tasks due today, overdue, and recently completed.

Uses OAuth2 tokens via the shared Google OAuth helper module.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import httpx

from vectorcode.src.connectors._abc import BaseConnector, Document, SyncStatus
from vectorcode.src.connectors.oauth import (
    load_tokens,
    refresh_google_token,
    resolve_google_credentials,
    save_tokens,
)
from vectorcode.src.vc_core.config import DEFAULT_CONFIG_DIR
from vectorcode.src.vc_core.registry import ConnectorRegistry

_TASKS_API_BASE = "https://tasks.googleapis.com/tasks/v1"
_DEFAULT_CREDENTIALS_PATH = str(DEFAULT_CONFIG_DIR / "connectors" / "google_tasks.json")

def _tasks_api_get(
    token: str, endpoint: str, params: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Call a Google Tasks API v1 endpoint."""
    resp = httpx.get(
        f"{_TASKS_API_BASE}/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()

@ConnectorRegistry.register("google_tasks")
class GoogleTasksConnector(BaseConnector):
    """Sync tasks from Google Tasks."""

    connector_id = "google_tasks"
    display_name = "Google Tasks"
    auth_type = "oauth"

    def __init__(self, *, credentials_path: str = "") -> None:
        self._credentials_path = Path(
            resolve_google_credentials(credentials_path or _DEFAULT_CREDENTIALS_PATH)
        )
        self._status = SyncStatus()

    def _get_access_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token, refreshing it first if it has
        expired (or if force_refresh is requested after a real 401).

        FL-033 (owner decision 2026-10-11, full build): mirrors
        strava.py's proactive-refresh-with-60s-margin pattern, using the
        shared refresh_google_token() helper (identical grant shape for
        every Google-based connector). Previously there was no expiry
        check or refresh at all, so sync() started failing with a 401
        after ~1h until the owner manually re-authenticated.
        """
        tokens = load_tokens(str(self._credentials_path)) or {}
        access_token = tokens.get("access_token") or tokens.get("token", "")
        expires_at = tokens.get("expires_at")

        needs_refresh = (
            force_refresh or expires_at is None or float(expires_at) <= time.time() + 60
        )
        if not needs_refresh:
            return access_token

        client_id = tokens.get("client_id")
        client_secret = tokens.get("client_secret")
        refresh_token = tokens.get("refresh_token")
        if not (client_id and client_secret and refresh_token):
            # No way to refresh (e.g. a pre-fix credentials file, or one
            # written by a flow that never persisted a refresh pair) --
            # fall back to whatever access_token is on disk and let the
            # API call itself raise if it's actually expired.
            return access_token

        refreshed = refresh_google_token(client_id, client_secret, refresh_token)
        tokens["access_token"] = refreshed.get("access_token", access_token)
        tokens["refresh_token"] = refreshed.get("refresh_token", refresh_token)
        if "expires_in" in refreshed:
            tokens["expires_at"] = time.time() + float(refreshed["expires_in"])
        save_tokens(str(self._credentials_path), tokens)
        return tokens["access_token"]

    def _api_get_with_retry(
        self, endpoint: str, params: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Call the Tasks API, retrying exactly once with a forced token
        refresh on a real 401 (FL-033's "retry behavior" -- covers the
        case where the proactive expiry check above said the token was
        still fresh, but Google rejected it anyway: clock skew, early
        manual revocation, etc.)."""
        token = self._get_access_token()
        try:
            return _tasks_api_get(token, endpoint, params=params or {})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 401:
                raise
            token = self._get_access_token(force_refresh=True)
            return _tasks_api_get(token, endpoint, params=params or {})

    def is_connected(self) -> bool:
        return self._credentials_path.exists()

    def disconnect(self) -> None:
        if self._credentials_path.exists():
            self._credentials_path.unlink()

    def sync(
        self, *, since: Optional[datetime] = None, cursor: Optional[str] = None
    ) -> Iterator[Document]:
        self._status = SyncStatus(state="syncing")
        try:
            task_lists = self._api_get_with_retry("users/@me/lists")
        except Exception as exc:
            self._status.state = "error"
            self._status.error = str(exc)
            raise

        for tl in task_lists.get("items", []):
            tl_id = tl["id"]
            tl_title = tl.get("title", "My Tasks")

            # Get tasks from this list, updated since cutoff
            params: Dict[str, str] = {
                "showCompleted": "true",
                "showHidden": "false",
            }
            if since:
                since_utc = (
                    since.replace(tzinfo=timezone.utc)
                    if since.tzinfo is None
                    else since.astimezone(timezone.utc)
                )
                params["updatedMin"] = since_utc.isoformat().replace("+00:00", "Z")

            try:
                tasks = self._api_get_with_retry(f"lists/{tl_id}/tasks", params=params)
            except Exception as exc:
                self._status.state = "error"
                self._status.error = str(exc)
                raise

            for task in tasks.get("items", []):
                due = task.get("due", "")
                status = task.get("status", "needsAction")

                ts = (
                    datetime.fromisoformat(
                        task.get("updated", "").replace("Z", "+00:00")
                    )
                    if task.get("updated")
                    else datetime.now()
                )

                yield Document(
                    doc_id=f"gtasks-{task['id']}",
                    source="google_tasks",
                    doc_type="task",
                    content=task.get("notes", ""),
                    title=task.get("title", "Untitled Task"),
                    timestamp=ts,
                    url=task.get("selfLink", ""),
                    metadata={
                        "task_list": tl_title,
                        "status": status,
                        "due": due,
                        "completed": task.get("completed", ""),
                    },
                )

        self._status.state = "idle"
        self._status.last_sync = datetime.now()

    def sync_status(self) -> SyncStatus:
        return self._status
