"""Test governor routing with novel queries to prove patterns generalize."""
import os
import sys
import time
import httpx
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

VECTOR_BASE = os.environ.get("VECTOR_EVAL_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("VECTOR_API_KEY", "").strip()
if not API_KEY:
    print("ERROR: VECTOR_API_KEY not set"); sys.exit(1)

# Novel queries NOT in the original eval set
QUERIES = [
    # (category, query, expected_district)
    ("languages_fr", "Quiz me on French vocabulary please", "languages"),
    ("startups_saas", "Help me validate my SaaS idea for dog walkers", "startups"),
    ("pattern_weekly", "Analyze my weekly productivity patterns", "pattern_detective"),
    ("brain_goals", "What are my current goals?", "brain"),
    ("design_login", "Sketch a login screen layout for my app", "design"),
]

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

print(f"Testing {len(QUERIES)} novel queries against {VECTOR_BASE}/command\n")
print(f"{'Category':<20} {'Expected':<20} {'Actual':<20} {'Match?'}")
print("-" * 70)

correct = 0
for category, query, expected in QUERIES:
    t0 = time.time()
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{VECTOR_BASE}/command",
                json={"text": query, "priority": "normal", "source": "generalization_test"},
                headers=headers,
            )
            latency = round(time.time() - t0, 2)
            data = r.json()
            district = data.get("district", "") or "None"
            match = "YES" if district == expected else "NO"
            if district == expected:
                correct += 1
            print(f"{category:<20} {expected:<20} {district:<20} {match}")
    except Exception as e:
        print(f"{category:<20} {expected:<20} ERROR: {e}")

print("-" * 70)
print(f"Result: {correct}/{len(QUERIES)} correct")
raise SystemExit(0 if correct == len(QUERIES) else 1)
