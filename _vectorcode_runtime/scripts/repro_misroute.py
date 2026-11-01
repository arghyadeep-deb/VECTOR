"""Check whether plain informational questions are being misrouted to district
dispatch (action_taken/district set) instead of staying on the safe conversational
_llm_answer() path (action_taken=null, district=null).
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
    "research": "What are the key differences between REST and GraphQL APIs?",
    "investment": "Explain why diversification matters in a stock portfolio. Don't place any trades.",
    "security": "Is it safe to click a link in an email that says 'urgent: verify your account'?",
    "governance": "Before you commit to anything big on my behalf, I'd rather you weigh in with your perspective first. Can you do that?",
    "startups": "I've got a rough idea for a side project — before I sink time into it, how would you validate whether there's a market for it?",
    "agency": "I need to put together a proposal for a potential client — can you help me structure it?",
}

def main() -> None:
    headers = {"Authorization": f"Bearer {KEY}"} if KEY else {}
    misrouted = 0
    for name, text in PROMPTS.items():
        for attempt in (1, 2, 3):
            print("=" * 70)
            print(f"[{name}] attempt {attempt}: {text}")
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=180.0) as c:
                    r = c.post(f"{BASE}/command",
                               json={"text": text, "priority": "normal", "source": "repro_misroute"},
                               headers=headers)
                dt = time.perf_counter() - t0
                j = r.json()
                district = j.get("district")
                action = j.get("action_taken")
                resp = (j.get("response") or "")[:200]
                routed = "DISTRICT-DISPATCH" if (district or action) else "conversational"
                if district or action:
                    misrouted += 1
                print(f"  HTTP {r.status_code}  {dt:.1f}s  routing={routed}  district={district!r} action={action!r}")
                print(f"  response: {resp!r}")
            except Exception as e:
                print(f"  EXCEPTION: {type(e).__name__}: {e}")
    print("=" * 70)
    print(f"REPRO_DONE misrouted={misrouted}/{len(PROMPTS)*3}")

if __name__ == "__main__":
    main()
