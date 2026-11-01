"""Repro for the 2 new lows in the post-fix eval: privacy and news_trends+memory_curator.
Both scored nonempty:0.0 -- checking if this is a real regression or transient flakiness.
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
    "privacy": "What data of mine do you store, and can I ask you to delete it?",
    "news_trends+memory_curator": "Give me today's one-line AI news headline, then tell me you've noted it for later.",
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
                               json={"text": text, "priority": "normal", "source": "repro_regr"},
                               headers=headers)
                dt = time.perf_counter() - t0
                print(f"  HTTP {r.status_code}   {dt:.1f}s")
                print(f"  raw body: {r.text[:700]}")
            except Exception as e:
                dt = time.perf_counter() - t0
                print(f"  EXCEPTION after {dt:.1f}s: {type(e).__name__}: {e}")
    print("=" * 70)
    print("REPRO_DONE")

if __name__ == "__main__":
    main()
