"""Phase A of the free-forever VECTOR eval: collect real responses from the
live backend for every golden dataset item. Deliberately does NOT call the
DeepEval/Ollama judge here — keeping "call VECTOR" and "call the judge model"
in separate phases avoids GPU VRAM thrashing (both use the same local Ollama
server; interleaving them forces a model swap on nearly every item, per
scripts/langsmith_vector_eval.py's documented 35+ minute stall from exactly
this failure mode).

Writes scripts/../deepeval_responses.json — consumed by deepeval_score.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception as e:
    print(f"[WARN] dotenv load failed: {e}")

import httpx
from scripts.golden_dataset import build_golden_dataset

VECTOR_BASE = os.environ.get("VECTOR_EVAL_BASE_URL", "http://127.0.0.1:8000")
VECTOR_API_KEY = os.environ.get("VECTOR_API_KEY", "")
OUT_PATH = ROOT / "deepeval_responses.json"


def ask_vector(query: str) -> dict:
    """Same endpoint/contract as scripts/langsmith_vector_eval.py::ask_vector
    (POST /command, Bearer auth, 150s timeout for provider-fallback chains,
    400+injection-detail treated as a correct block, not an error)."""
    headers = {"Authorization": f"Bearer {VECTOR_API_KEY}"} if VECTOR_API_KEY else {}
    t0 = time.time()
    try:
        with httpx.Client(timeout=150.0) as client:
            r = client.post(
                f"{VECTOR_BASE}/command",
                json={"text": query, "priority": "normal", "source": "deepeval_eval"},
                headers=headers,
            )
            if r.status_code == 400:
                detail = ""
                try:
                    detail = (r.json() or {}).get("detail", "")
                except Exception:
                    detail = r.text
                if "injection" in detail.lower() or "blocked" in detail.lower():
                    return {
                        "response": (
                            "I can't help with that — it looks like an attempt "
                            f"to override my instructions, so I've blocked it. ({detail})"
                        ),
                        "success": True,
                        "district": None,
                        "action_taken": "blocked_prompt_injection",
                        "http_status": 400,
                        "latency_s": round(time.time() - t0, 2),
                    }
            r.raise_for_status()
            data = r.json()
            return {
                "response": data.get("response", ""),
                "success": data.get("action_taken") is not None or bool(data.get("response")),
                "district": data.get("district"),
                "action_taken": data.get("action_taken"),
                "http_status": r.status_code,
                "latency_s": round(time.time() - t0, 2),
            }
    except Exception as e:
        return {"response": "", "success": False, "error": str(e), "latency_s": round(time.time() - t0, 2)}


def main() -> None:
    dataset = build_golden_dataset()
    print(f"Collecting real VECTOR responses for {len(dataset)} golden items "
          f"against {VECTOR_BASE} ...")
    if not VECTOR_API_KEY:
        print("[WARN] VECTOR_API_KEY not set — requests will go out unauthenticated "
              "and likely fail if the API requires auth.")

    results = []
    for i, item in enumerate(dataset, start=1):
        print(f"[{i}/{len(dataset)}] ({item['tier']}/{item['category']}) "
              f"{item['input'][:70]!r}...", end=" ")
        result = ask_vector(item["input"])
        print(f"-> {result['latency_s']}s, "
              f"{'OK' if result.get('response') else 'EMPTY/ERROR'}")
        results.append({
            "input": item["input"],
            "category": item["category"],
            "tier": item["tier"],
            "check": item["check"],
            "criteria": item["criteria"],
            "vector_meta": item["meta"],
            **result,
        })
        # Small gap between requests — be a polite client, not a hammer,
        # and give any transient provider rate-limit a moment to clear.
        time.sleep(0.5)

    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    n_empty = sum(1 for r in results if not r.get("response"))
    print(f"\nWrote {len(results)} collected responses to {OUT_PATH}")
    print(f"Empty/error responses: {n_empty}/{len(results)} "
          f"(these will auto-fail scoring — worth a retry pass if this is high)")
    print("\nDEEPEVAL_COLLECT_DONE_MARKER")


if __name__ == "__main__":
    main()
