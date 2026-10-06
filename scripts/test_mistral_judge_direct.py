"""Direct, unconditional test of the new Mistral judge path (KNOWN_ISSUES #24)
— bypasses Gemini entirely so a Gemini success can't mask a broken Mistral call.
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception as e:
    print(f"[WARN] dotenv load failed: {e}")

from scripts.langsmith_vector_eval import _judge_via_mistral, _judge_prompt, MISTRAL_API_KEY, MISTRAL_MODEL

print(f"MISTRAL_API_KEY loaded: {bool(MISTRAL_API_KEY)}  (len={len(MISTRAL_API_KEY)})")
print(f"MISTRAL_MODEL: {MISTRAL_MODEL}")

prompt = _judge_prompt(
    "What is 2+2?",
    "2+2 equals 4.",
)
print("Calling _judge_via_mistral() directly...")
result = _judge_via_mistral(prompt)
print("RESULT:", result)
if result and "score" in result:
    print(f"MISTRAL_JUDGE_WORKS score={result['score']} reasoning={result.get('reasoning')}")
    exit_code = 0
else:
    print("MISTRAL_JUDGE_FAILED — returned None or unparseable")
    exit_code = 1
print("TEST_DONE_MARKER")
raise SystemExit(exit_code)
