# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------


__all__ = [
    "parse_search_query",
    "ParsedSearch",
]

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# Matches operator:value or operator:"quoted value"
_OPERATOR_RE = re.compile(
    r'\b(from|to|subject|in|is|has|before|after):(?:"([^"]*?)"|(\S+))',
    re.IGNORECASE,
)


@dataclass
class ParsedSearch:
    query: str = ""
    from_addr: Optional[str] = None
    to_addr: Optional[str] = None
    subject: Optional[str] = None
    folder: Optional[str] = None
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    has_attachment: Optional[bool] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None


def _normalize_date(value: str) -> Optional[str]:
    # None of these 3 formats parse a timezone -- strptime always returns a
    # NAIVE datetime here. Appending "Z" fabricated a UTC marker the input
    # never specified, and search_emails() string-compares this directly
    # against the emails.date column, which is stored via naive local
    # datetime.now().isoformat() (no "Z") -- the mismatched suffix made
    # before:/after: filters compare unreliably at boundary timestamps
    # (e.g. "...00.000000" sorts before "...00Z" lexicographically, even
    # for the same nominal moment). Dropping the fabricated "Z" matches the
    # real storage format.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            continue
    return None


def parse_search_query(input_str: str) -> ParsedSearch:
    """Parse a Gmail-style search string into structured filters.

    Supported: from:, to:, subject:, in:, is:, has:, before:, after:
    Quoted values supported: from:"John Doe"
    Remaining text becomes the free-text query.
    """
    result = ParsedSearch()
    remaining = input_str

    matches = []
    for m in _OPERATOR_RE.finditer(input_str):
        op = m.group(1).lower()
        value = m.group(2) if m.group(2) is not None else m.group(3)
        matches.append((m.group(0), op, value))

    for full_match, _, _ in matches:
        remaining = remaining.replace(full_match, "", 1)

    result.query = re.sub(r"\s+", " ", remaining).strip()

    for _, op, value in matches:
        if op == "from":
            result.from_addr = value
        elif op == "to":
            result.to_addr = value
        elif op == "subject":
            result.subject = value
        elif op == "in":
            result.folder = value.lower()
        elif op == "is":
            v = value.lower()
            if v == "unread":
                result.is_read = False
            elif v == "read":
                result.is_read = True
            elif v == "starred":
                result.is_starred = True
            elif v == "unstarred":
                result.is_starred = False
        elif op == "has":
            if value.lower() == "attachment":
                result.has_attachment = True
        elif op == "before":
            result.date_end = _normalize_date(value)
        elif op == "after":
            result.date_start = _normalize_date(value)

    return result


if __name__ == "__main__":
    r = parse_search_query('from:alice@example.com subject:"Hello World" is:unread invoice')
    assert r.from_addr == "alice@example.com"
    assert r.subject == "Hello World"
    assert r.is_read is False
    assert r.query == "invoice"

    r2 = parse_search_query("has:attachment before:2025-01-01")
    assert r2.has_attachment is True
    assert r2.date_end is not None
    print("✅ search.py OK")
