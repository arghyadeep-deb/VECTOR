"""Regression for districts/privacy/privacy_enforcer.py PrivacyEnforcer.redact_pii().

The LLM "catch anything pattern-matching missed" pass applied its reported
`additional_finds` by slicing redacted_text[:start] + placeholder +
redacted_text[end:]. Two problems made this unsound:

1. The LLM was shown only redacted_text[:300] (a truncated PREVIEW) in the
   prompt, so any start/end it returns describes positions in that preview,
   not necessarily the live string being sliced.
2. Applying multiple finds in list order mutates redacted_text on each
   iteration (the placeholder's length almost never matches the original
   match's length), so every subsequent item's start/end -- computed by the
   LLM against the pre-mutation text -- is stale and slices the wrong
   location, corrupting the text and typically leaving the real PII in place
   unredacted.

Fixed by matching on the LLM's reported `value` text via str.replace()
instead of trusting character offsets at all -- immune to both problems.
"""
from __future__ import annotations

from unittest.mock import patch

import districts.privacy.privacy_enforcer as mod


def test_multiple_additional_finds_do_not_corrupt_each_other():
    agent = mod.PrivacyEnforcer()

    # No pattern-based PII in this text -- forces the test down the
    # LLM-additional-finds path exclusively.
    text = "Contact ABC123 or XYZ789 for details."

    # Offsets as the LLM would compute them against the ORIGINAL text (both
    # values are real substrings at these positions in `text`).
    start1, end1 = text.index("ABC123"), text.index("ABC123") + len("ABC123")
    start2, end2 = text.index("XYZ789"), text.index("XYZ789") + len("XYZ789")

    fake_response = (
        '{"additional_finds": ['
        f'{{"type": "custom1", "start": {start1}, "end": {end1}, "value": "ABC123"}}, '
        f'{{"type": "custom2", "start": {start2}, "end": {end2}, "value": "XYZ789"}}'
        ']}'
    )

    with patch.object(mod.PrivacyEnforcer, "_call_ollama", return_value=fake_response):
        result = agent.redact_pii(text)

    redacted = result["redacted_text"]
    assert "ABC123" not in redacted, f"ABC123 survived redaction: {redacted!r}"
    assert "XYZ789" not in redacted, f"XYZ789 survived redaction: {redacted!r}"
    assert "[CUSTOM1_REDACTED]" in redacted
    assert "[CUSTOM2_REDACTED]" in redacted


if __name__ == "__main__":
    test_multiple_additional_finds_do_not_corrupt_each_other()
    print("✅ test_privacy_enforcer_redact_pii_offset_corruption.py OK")
