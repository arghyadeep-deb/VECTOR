"""Repro/verification for #21-#23 fixes, plus a second attempt at catching the
'200' / "Here's" truncation bugs from TIER2 with district/action_taken visible
so we can see WHICH agent produced them if they recur.
"""
from __future__ import annotations
import os, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import httpx
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

BASE = os.environ.get("VECTOR_EVAL_BASE_URL", "http://127.0.0.1:8000")
KEY = os.environ.get("VECTOR_API_KEY", "")

PROMPTS = {
    # #23 primary bug: multi-intent hijack by "remind me"
    "investment+safety": "Give me a beginner-investor mindset tip, and remind me clearly that you can't place real trades.",
    # #23 ride-along: '200' leak
    "news_trends+memory_curator": "Give me today's one-line AI news headline, then tell me you've noted it for later.",
    # #23 ride-along: "Here's" truncation
    "coding+qa": "Write a tiny Python function to validate an email address, and tell me how you'd test it.",
    # #23 ride-along: "Empty response from LLM" / governance combo
    "projects+coding": "Look at my VECTOR project status and tell me one concrete coding task to do next.",
    # #21 closed-database path
    "overwrite_note": "Note down that my exam is next Friday so I don't forget.",
    # #22 privacy misroute
    "privacy": "What data of mine do you store, and can I ask you to delete it?",
}

def main() -> None:
    headers = {"Authorization": f"Bearer {KEY}"} if KEY else {}
    for name, text in PROMPTS.items():
        for attempt in (1, 2, 3, 4):
            print("=" * 70)
            print(f"[{name}] attempt {attempt}: {text}")
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=180.0) as c:
                    r = c.post(f"{BASE}/command",
                               json={"text": text, "priority": "normal", "source": "repro_final"},
                               headers=headers)
                dt = time.perf_counter() - t0
                print(f"  HTTP {r.status_code}   {dt:.1f}s")
                print(f"  raw body: {r.text[:900]}")
            except Exception as e:
                dt = time.perf_counter() - t0
                print(f"  EXCEPTION after {dt:.1f}s: {type(e).__name__}: {e}")
    print("=" * 70)
    print("REPRO_DONE")

if __name__ == "__main__":
    main()
