"""Output redaction — strip sensitive data from model outputs."""

import re
from typing import Optional

_API_KEY_PATTERN = re.compile(r'(?i)(api[_-]?key|token|secret|password|auth|credential)[=:]\s*["\']?[A-Za-z0-9_-]{16,}["\']?')
_URL_PATTERN = re.compile(r'https?://[^\s]+')
_EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')


def redact(text: str, preserve_urls: bool = False, preserve_emails: bool = False) -> str:
    text = _API_KEY_PATTERN.sub(r'\1=***REDACTED***', text)
    if not preserve_urls:
        text = _URL_PATTERN.sub('***URL***', text)
    if not preserve_emails:
        text = _EMAIL_PATTERN.sub('***EMAIL***', text)
    return text


def redact_dict(data: dict, keys_to_redact: Optional[list[str]] = None) -> dict:
    keys_to_redact = keys_to_redact or ["api_key", "token", "secret", "password", "authorization"]
    result = {}
    for k, v in data.items():
        if any(s in k.lower() for s in keys_to_redact):
            result[k] = "***REDACTED***"
        elif isinstance(v, dict):
            result[k] = redact_dict(v, keys_to_redact)
        elif isinstance(v, str):
            result[k] = redact(v)
        else:
            result[k] = v
    return result
