"""One-time Gmail OAuth setup for VECTOR.

`districts/communications/email_intelligence.py` and the email agent read Gmail
via an authorized-user token at ``~/.vector/gmail_token.json``. That token is
produced by running this module once:

    pip install google-auth-oauthlib        # one-time, if not already installed
    python -m core.integrations.gmail_auth

Prerequisites (owner, one-time — cannot be done from code):
  1. Create a Google Cloud project, enable the **Gmail API**.
  2. Configure the OAuth consent screen (External, add your own Gmail as a test user).
  3. Create an **OAuth client ID** of type *Desktop app*, download the JSON.
  4. Save it as ``~/.vector/google_credentials.json``.

Then run the command above; a browser opens for consent and the token is written
to ``~/.vector/gmail_token.json``. After that, VECTOR reads/sends your Gmail.

Scopes requested: read + modify (mark read / label) + send — everything VECTOR's
email features use. Narrow them in SCOPES below if you want read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # read + mark-read/label
    "https://www.googleapis.com/auth/gmail.send",     # outbound (gated by VECTOR)
]

_VECTOR_DIR = Path.home() / ".vector"
CREDENTIALS_PATH = _VECTOR_DIR / "google_credentials.json"
TOKEN_PATH = _VECTOR_DIR / "gmail_token.json"


def authorize() -> Path:
    """Run the installed-app OAuth flow and write the token. Returns the token path.

    Raises a clear, actionable error if the OAuth library is missing or the
    credentials file hasn't been placed yet — so the failure tells you exactly
    what to do rather than a bare ImportError/FileNotFoundError.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise SystemExit(
            "google-auth-oauthlib is not installed.\n"
            "  Run:  pip install google-auth-oauthlib\n"
            "  then: python -m core.integrations.gmail_auth"
        ) from e

    if not CREDENTIALS_PATH.exists():
        raise SystemExit(
            f"OAuth client file not found: {CREDENTIALS_PATH}\n"
            "  1. Google Cloud Console → enable Gmail API → create an OAuth client "
            "(Desktop app) → download the JSON.\n"
            f"  2. Save it as {CREDENTIALS_PATH}\n"
            "  3. Re-run: python -m core.integrations.gmail_auth"
        )

    _VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return TOKEN_PATH


def is_connected() -> bool:
    """True if a Gmail token already exists (VECTOR can talk to Gmail)."""
    return TOKEN_PATH.exists()


def main() -> int:
    if is_connected():
        print(f"Gmail already connected — token at {TOKEN_PATH}")
        print("Delete it and re-run to re-authorize a different account.")
        return 0
    path = authorize()
    print(f"Gmail connected. Token written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
