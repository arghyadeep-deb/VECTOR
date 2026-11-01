"""Live repro for KNOWN_ISSUES #25 (communications misroute to content
district) and #26 ('remind me' rhetorical opener triggering a literal
reminder), against the real running backend post-fix.
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
    "27_whatsapp_draft": "Draft a short WhatsApp message to my friend saying I'll be 15 minutes late.",
}

def main() -> None:
    headers = {"Authorization": f"Bearer {KEY}"} if KEY else {}
    for name, text in PROMPTS.items():
        for attempt in range(1, 9):
            print("=" * 70)
            print(f"[{name}] attempt {attempt}: {text}")
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=180.0) as c:
                    r = c.post(f"{BASE}/command",
                               json={"text": text, "priority": "normal", "source": "repro_25_26"},
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
