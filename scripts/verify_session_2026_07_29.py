"""Live verification for the 2026-07-29 session's fixes (KNOWN_ISSUES #31):
  1. set_reminder confirmation now says what/when, not a generic line.
  2. The rhetorical "remind me <question>" guard still doesn't fire a real reminder.
  3. documentation-district changelog request no longer leaks raw invoke_tool(...) syntax.
  4. security+communications capability-match caveat (or a real answer).
  5. growth+content+safety capability-match caveat (or a real answer), not an unrelated script.
  6. agency proposal request correctly reaches proposal_strategist (already-fixed, re-confirming live).
  7. session_id continuity: a second /command call with the same session_id can see the first turn.

Run via RUN_VERIFY_TODAY.bat (writes to verify_session_2026_07_29.log).
Requires the live API on :8000 — this only runs from the owner's machine.
"""
from __future__ import annotations
import os, sys, time, uuid
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


def post(client: httpx.Client, headers: dict, text: str, session_id: str | None = None) -> dict:
    body = {"text": text, "priority": "normal", "source": "verify_2026_07_29"}
    if session_id:
        body["session_id"] = session_id
    t0 = time.perf_counter()
    r = client.post(f"{BASE}/command", json=body, headers=headers)
    dt = time.perf_counter() - t0
    print(f"  HTTP {r.status_code}   {dt:.1f}s")
    print(f"  raw body: {r.text[:1200]}")
    try:
        return r.json()
    except Exception:
        return {}


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")


def main() -> None:
    headers = {"Authorization": f"Bearer {KEY}"} if KEY else {}
    with httpx.Client(timeout=180.0) as c:

        print("=" * 70)
        print("[1/7] set_reminder confirmation now says what/when")
        resp = post(c, headers, "remind me to call mom at 5pm")
        text = str(resp.get("response", ""))
        check("mentions the actual reminder content", "call mom" in text.lower(), text[:200])
        check("not the old generic line only",
              text.strip() != "Executed: set_reminder. You'll be notified.", text[:200])

        print("=" * 70)
        print("[2/7] rhetorical 'remind me <question>' guard still holds")
        resp = post(c, headers, "Remind me -- who do I usually talk to about coding help?")
        text = str(resp.get("response", ""))
        check("did NOT fire a literal set_reminder", resp.get("action_taken") != "set_reminder",
              f"action_taken={resp.get('action_taken')!r}")

        print("=" * 70)
        print("[3/7] documentation changelog — no raw invoke_tool(...) leak")
        resp = post(c, headers, "Can you generate a changelog of everything that's changed in the VECTOR codebase recently?")
        text = str(resp.get("response", ""))
        check("no invoke_tool( leak", "invoke_tool(" not in text, text[:200])
        check("routed to documentation (not coding)", resp.get("district") in (None, "documentation"),
              f"district={resp.get('district')!r}")

        print("=" * 70)
        print("[4/7] security+communications — bank OTP scam safety question")
        resp = post(c, headers, "I got a message asking for my bank OTP to 'verify' my account — is this a scam?")
        text = str(resp.get("response", ""))
        check("not a bare inbox-status stub with no caveat/relevance",
              not (("unread inbox" in text.lower() or "total emails" in text.lower())
                   and "heads up" not in text.lower() and "capability" not in text.lower()),
              text[:200])

        print("=" * 70)
        print("[5/7] growth+content+safety — Instagram growth-plan ask")
        resp = post(c, headers, "Give me a safe, realistic plan to grow my Instagram following this month.")
        text = str(resp.get("response", ""))
        check("not an unrelated YouTube script with no caveat",
              not ("youtube" in text.lower() and "heads up" not in text.lower() and "capability" not in text.lower()),
              text[:200])

        print("=" * 70)
        print("[6/7] agency — client proposal request")
        resp = post(c, headers, "help me draft a proposal for a client")
        text = str(resp.get("response", ""))
        check("routed to agency (not content)", resp.get("district") in (None, "agency"),
              f"district={resp.get('district')!r}")
        check("not an unrelated social-media-trends essay",
              "2024 social media trends" not in text.lower(), text[:200])

        print("=" * 70)
        print("[7/7] session_id continuity — second call sees the first turn")
        sid = f"verify-{uuid.uuid4().hex[:8]}"
        post(c, headers, "Remember this for our conversation: my favorite color is teal.", session_id=sid)
        resp = post(c, headers, "What did I just tell you my favorite color was?", session_id=sid)
        text = str(resp.get("response", ""))
        check("recalled 'teal' from the same session", "teal" in text.lower(), text[:200])

    print("=" * 70)
    print("VERIFY_DONE")


if __name__ == "__main__":
    main()
