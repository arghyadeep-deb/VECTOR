"""Real Gmail API client — owner request 2026-10-25: "for email use gmail".

2026-10-25 (corrected): originally wired to a brand-new collections-DB
token store + new OAuth app, but the owner had ALREADY completed a real
Google consent on 2026-10-13 for FL-033 ("vectorcode connectors" — Gmail,
Calendar, Drive, Tasks, Contacts, one consent for all of them), with a
live access_token + refresh_token already sitting in
~/.vector/connectors/google.json. Re-pointed at THAT real, already-
authorized token store (via vectorcode/src/connectors/oauth.py's
get_valid_google_token(), which also handles refresh) instead of asking
for a second, redundant OAuth setup. This replaces the previously-dormant
IMAP path (districts/communications/email_agent.py's poll_inbox()) with
the real Gmail API, matching .claude/rules/libraries.md's original
intended design ("google-api-python-client — Gmail + Calendar").

Degrades gracefully (returns a clear "not configured" error) when no
token exists yet — never crashes.
"""
import sys
import base64
from email.mime.text import MIMEText

from loguru import logger

__all__ = ["GmailClient"]


class GmailClient:
    """Thin wrapper around the Gmail API — read recent messages, send a message."""

    def __init__(self):
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from googleapiclient.discovery import build
            import google.oauth2.credentials as _gcreds
            from vectorcode.src.connectors.oauth import get_valid_google_token

            tokens = get_valid_google_token()
            if not tokens:
                logger.warning("[VECTOR][gmail] not connected — no Google OAuth token found "
                                "(~/.vector/connectors/google.json)")
                return None
            credentials = _gcreds.Credentials(
                token=tokens.get("access_token"),
                refresh_token=tokens.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=tokens.get("client_id", ""),
                client_secret=tokens.get("client_secret", ""),
                scopes=["https://www.googleapis.com/auth/gmail.readonly",
                        "https://www.googleapis.com/auth/gmail.send"],
            )
            self._service = build("gmail", "v1", credentials=credentials)
            logger.info("[VECTOR][gmail] service ready (FL-033 shared Google token)")
            return self._service
        except ImportError:
            logger.warning("[VECTOR][gmail] google-api-python-client not installed")
            return None
        except Exception as e:
            logger.warning(f"[VECTOR][gmail] service init failed: {e}")
            return None

    def list_recent(self, limit: int = 10, query: str = "") -> dict:
        """List recent messages (default: inbox). `query` is a real Gmail
        search string (e.g. "is:unread", "from:someone@example.com")."""
        svc = self._get_service()
        if svc is None:
            return {"messages": [], "error": "Gmail not connected — complete Google OAuth setup first"}
        try:
            resp = svc.users().messages().list(
                userId="me", maxResults=max(1, min(50, limit)),
                q=query or "in:inbox",
            ).execute()
            ids = [m["id"] for m in resp.get("messages", [])]
            out = []
            for mid in ids:
                msg = svc.users().messages().get(
                    userId="me", id=mid, format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                out.append({
                    "id": mid,
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", "(no subject)"),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                })
            return {"messages": out}
        except Exception as e:
            logger.error(f"[VECTOR][gmail] list_recent error: {e}")
            return {"messages": [], "error": str(e)}

    def send(self, to: str, subject: str, body: str) -> dict:
        """Send a real email via the owner's Gmail account."""
        svc = self._get_service()
        if svc is None:
            return {"sent": False, "error": "Gmail not connected — complete Google OAuth setup first"}
        if not to:
            return {"sent": False, "error": "no recipient given"}
        try:
            msg = MIMEText(body or "")
            msg["to"] = to
            msg["subject"] = subject or "(no subject)"
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
            logger.info(f"[VECTOR][gmail] sent message id={sent.get('id')} to={to}")
            return {"sent": True, "id": sent.get("id", "")}
        except Exception as e:
            logger.error(f"[VECTOR][gmail] send error: {e}")
            return {"sent": False, "error": str(e)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    client = GmailClient()
    result = client.list_recent(limit=1)
    ok = "error" not in result or "not connected" in result.get("error", "")
    print("✅ gmail_client OK" if ok else f"❌ FAILED: {result}")
