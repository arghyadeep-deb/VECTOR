"""Diagnose tier 6 empty responses — test each failing query against live backend."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

for _s in ("stdout", "stderr"):
    _stream = getattr(sys, _s, None)
    if _stream and hasattr(_stream, "reconfigure"):
        try: _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import httpx

VECTOR_BASE = os.environ.get("VECTOR_EVAL_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("VECTOR_API_KEY", "").strip()

# The 10 tier 6 queries that returned empty
QUERIES = [
    ("reflection", "Can you look back at how my week's actually gone and tell me what patterns you see?"),
    ("karpathy_lab", "I want to do a focused 30-minute deep-learning study session on transformers. What should I cover?"),
    ("languages", "I've got a few spare minutes - can you quiz me on some Hindi vocabulary?"),
    ("brain", "Honestly, what do you currently think my main goals are, and how am I doing on them?"),
    ("pattern_detective", "Looking at my daily habits lately, is there any pattern in when I'm most productive?"),
    ("startups", "I've got a rough idea for a side project - before I sink time in, can you help me think through the market?"),
    ("ops", "Is everything on your end running smoothly right now, or are there any issues I should know about?"),
    ("data_analytics", "Can you put together a quick report on how you've been performing lately?"),
    ("design", "I'm mocking up a simple settings screen - can you sketch out what the layout should look like?"),
    ("science", "If I mixed baking soda and vinegar in a sealed bottle, what would happen and why?"),
]

def _diagnostic_exit_code(verdicts: list[str]) -> int:
    """A diagnostic gate succeeds only when every query returned content."""
    return 0 if verdicts and all(v == "OK" for v in verdicts) else 1


def main() -> int:
    if not API_KEY:
        print("ERROR: VECTOR_API_KEY not set")
        return 1
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    verdicts: list[str] = []
    print(f"Testing {len(QUERIES)} tier 6 queries against {VECTOR_BASE}/command\n")

    for category, query in QUERIES:
        t0 = time.time()
        try:
            with httpx.Client(timeout=120.0) as client:
                r = client.post(
                    f"{VECTOR_BASE}/command",
                    json={"text": query, "priority": "normal", "source": "tier6_diag"},
                    headers=headers,
                )
                latency = round(time.time() - t0, 2)
                status = r.status_code
                try:
                    data = r.json()
                except Exception:
                    data = {"raw": r.text[:300]}
                response = data.get("response", "")
                district = data.get("district", "")
                action = data.get("action_taken", "")
                resp_len = len(response)
                preview = response[:150].replace("\n", " ") if response else "<EMPTY>"
                verdict = "OK" if r.is_success and resp_len > 10 else "EMPTY"
                verdicts.append(verdict)
                print(f"[{verdict}] {category} | HTTP {status} | {latency}s | district={district} | action={action}")
                print(f"  ({resp_len} chars) {preview}")
                print()
        except Exception as e:
            verdicts.append("ERROR")
            latency = round(time.time() - t0, 2)
            print(f"[ERROR] {category} | {latency}s | {e}\n")
    return _diagnostic_exit_code(verdicts)


if __name__ == "__main__":
    raise SystemExit(main())
