# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

from __future__ import annotations

import re
from typing import List, Tuple

_CREDENTIAL_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"sk-[a-zA-Z0-9_-]{20,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    # Was missing ghs_/ghr_/github_pat_ -- scanner.py's SecretScanner
    # already covers all five GitHub token prefixes.
    ("github_token", re.compile(r"(?:ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}")),
    ("slack_token", re.compile(r"xox[bpors]-[0-9A-Za-z\-]+")),
    ("bearer_token", re.compile(r"Bearer\s+[a-zA-Z0-9_\-.]{20,}")),
    # The following were entirely absent -- a Stripe key, a DB connection
    # string, a PEM private key block, or a plain password=/api_key=
    # assignment could previously reach log output unredacted even though
    # scanner.py's SecretScanner (used for outbound-content scanning) has
    # always covered all of them.
    ("stripe_key", re.compile(r"(?:sk|pk)_(?:test|live)_[A-Za-z0-9]{20,}")),
    ("db_connection_string", re.compile(r"(?:postgres|mysql|mongodb|redis)://\S{10,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----")),
    (
        "password_assignment",
        re.compile(r"""(?:password|passwd|pwd)\s*[=:]\s*['"]([^'"]{4,})['"]"""),
    ),
    (
        "generic_api_key",
        re.compile(r"""(?:api_key|secret_key|auth_token)\s*[=:]\s*['"]([^'"]{8,})['"]"""),
    ),
]

class CredentialStripper:
    """Redacts credentials from text using compiled regex patterns."""

    def __init__(self) -> None:
        self._patterns = _CREDENTIAL_PATTERNS

    def strip(self, text: str) -> str:
        for label, pattern in self._patterns:
            text = pattern.sub(f"[REDACTED:{label}]", text)
        return text

def wrap_tool_output(tool_name: str, content: str, success: bool = True) -> str:
    status = "success" if success else "error"
    header = f'<tool_result name="{tool_name}" status="{status}">'
    return f"{header}\n{content}\n</tool_result>"
