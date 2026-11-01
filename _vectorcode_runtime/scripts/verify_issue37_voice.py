"""Scripted, no-audio-required verification for KNOWN_ISSUES.md issue #37.

2026-07-29 CORRECTION: an earlier version of this script assumed
`core.personality` doesn't exist in the codebase and never actually called
PersonalityEngine().process() even when the import succeeded — it only
checked whether the import *raised*. That was wrong: core.personality is a
full, working package. This version calls the REAL production code path
(the same one core/voice/realtime.py::_stream_chat and
core/api/routers/voice_ws.py use) so the test actually reflects what ships.

Checks:
1. core.personality imports and PersonalityEngine().process() returns a
   real, non-empty system_prompt.
2. That system_prompt (built from core/personality/characters/vector.json's
   `rules` array) now contains the English-only + spoken-text-safety rules
   added to fix issue #37.
3. A real LLM call, given a plain Hindi question, comes back in English
   after sanitize_for_speech() — using the REAL PersonalityEngine prompt,
   not a hardcoded fallback string.
4. sanitize_for_speech() strips markdown from a synthetic dirty string.
5. A HARDER case: an explicit "reply in Hindi" demand.
"""
from __future__ import annotations
import sys
import asyncio
import re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception as e:
    print(f"[WARN] dotenv load failed: {e}")

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def devanagari_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    dev = sum(1 for c in letters if _DEVANAGARI_RE.match(c))
    return dev / len(letters)


async def main() -> int:
    print("=== Step 1: core.personality import + PersonalityEngine().process() ===")
    system_prompt = ""
    try:
        from core.personality import PersonalityEngine
        pe = PersonalityEngine()
        result = pe.process("आज का मौसम कैसा रहेगा?")
        system_prompt = result.get("system_prompt", "")
        print(f"OK: core.personality works. system_prompt length: {len(system_prompt)} chars")
    except Exception as e:
        print(f"FAIL: core.personality failed ({type(e).__name__}: {e})")
        return 1

    print("\n=== Step 2: system_prompt contains the fixed vector.json rules ===")
    assert "English" in system_prompt, "missing English-only instruction!"
    assert "read aloud" in system_prompt.lower() or "text-to-speech" in system_prompt.lower(), \
        "missing spoken-text-safety instruction!"
    print("OK: system_prompt contains English-only + spoken-text-safety instructions")
    print(f"\nsystem_prompt non-empty: {bool(system_prompt)} ({len(system_prompt)} chars)")

    from core.inference.provider_client import ProviderClient
    from core.loop.context_engine import ContextEngine
    from core.voice.tts import sanitize_for_speech
    hydration = ContextEngine().session_hydration_prompt()

    print("\n=== Step 3: real LLM call, plain Hindi question, no explicit language demand ===")
    messages = [
        {"role": "system", "content": hydration + "\n\n" + system_prompt},
        {"role": "user", "content": "आज का मौसम कैसा रहेगा?"},
    ]
    result = await ProviderClient().chat(
        messages=messages, tier="conversation", max_tokens=300,
        temperature=0.7, caller_id="verify_issue37",
    )
    raw = result.content or ""
    clean = sanitize_for_speech(raw)
    print(f"RAW:\n{raw}\n")
    print(f"WHAT TTS WOULD SPEAK:\n{clean}\n")
    ratio = devanagari_ratio(clean)
    print(f"Devanagari ratio: {ratio:.2%}")
    print("RESULT: PASS (English)" if ratio < 0.2 else "RESULT: FAIL (still Hindi)")
    failed = ratio >= 0.2

    print("\n=== Step 4: sanitize_for_speech() unit check on a synthetic dirty string ===")
    dirty = "**Sure**, here's the plan:\n- First item\n- Second item\n\n# Heading\nUse `code` and [a link](http://x.com)."
    clean2 = sanitize_for_speech(dirty)
    print(f"DIRTY: {dirty!r}")
    print(f"CLEAN: {clean2!r}")
    leaked = [ch for ch in "*_`#[]()" if ch in clean2]
    print("RESULT: PASS (no markdown symbols leaked)" if not leaked else f"RESULT: FAIL (leaked: {leaked})")
    failed = failed or bool(leaked)

    print("\n=== Step 5 (harder case): explicit 'reply in Hindi' demand ===")
    messages2 = [
        {"role": "system", "content": hydration + "\n\n" + system_prompt},
        {"role": "user", "content": "कृपया हिंदी में ही जवाब दें। आपका नाम क्या है?"},
    ]
    result2 = await ProviderClient().chat(
        messages=messages2, tier="conversation", max_tokens=200,
        temperature=0.7, caller_id="verify_issue37b",
    )
    raw2 = result2.content or ""
    clean3 = sanitize_for_speech(raw2)
    print(f"RAW:\n{raw2}\n")
    print(f"WHAT TTS WOULD SPEAK:\n{clean3}\n")
    ratio2 = devanagari_ratio(clean3)
    print(f"Devanagari ratio: {ratio2:.2%}")
    if ratio2 < 0.2:
        print("RESULT: PASS (system prompt enforced English despite explicit Hindi demand)")
    else:
        print("RESULT: KNOWN GAP — explicit Hindi request defeats prompt-only enforcement on the streaming voice path (no deterministic backstop on this path; see KNOWN_ISSUES #37)")

    print("\nVERIFY_ISSUE37_DONE_MARKER")
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
