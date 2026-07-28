"""Regression test: core/api/routers/intelligence.py must degrade to a 503
JSON payload when the shadowbroker sidecar is unreachable, not crash into a
raw 500.

Found by browser dogfood (2026-07-17): shadowbroker is OFF BY DEFAULT (owner
rule, 2026-07-16: single-server unless VECTOR_SIDECARS is set), so every one
of the /intelligence/* read endpoints threw an unhandled httpx.ConnectError
straight out of the FastAPI handler -> bare "500 Internal Server Error" in the
browser. Confirmed live via direct repro (get_summary() raised
httpx.ConnectError with a full traceback through vectorintel_agent.py ->
sb_query.py). The fix wraps every read endpoint in `_safe(...)`, which
catches httpx.ConnectError/TimeoutException/ReadError and returns
JSONResponse(..., status_code=503) -- mirroring the pattern already used by
GET /sb/health.

Run: python tests/test_intelligence_graceful_degradation.py  (or via pytest)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from core.api.routers.intelligence import _safe


async def _boom():
    raise httpx.ConnectError("all connection attempts failed")


async def _boom_timeout():
    raise httpx.TimeoutException("timed out")


async def _ok():
    return {"status": "ok", "layers": 3}


async def _unrelated_error():
    raise ValueError("not a connectivity problem")


def test_connect_error_degrades_to_503():
    result = asyncio.run(_safe(_boom()))
    assert result.status_code == 503, f"expected 503, got {result.status_code}"


def test_timeout_degrades_to_503():
    result = asyncio.run(_safe(_boom_timeout()))
    assert result.status_code == 503


def test_healthy_call_passes_through_unchanged():
    result = asyncio.run(_safe(_ok()))
    assert result == {"status": "ok", "layers": 3}


def test_unrelated_exceptions_still_propagate():
    """_safe() must only catch CONNECTIVITY failures. Swallowing every
    exception would hide real bugs (bad params, logic errors) behind a
    misleading 'service unavailable'."""
    try:
        asyncio.run(_safe(_unrelated_error()))
        raise AssertionError("ValueError should have propagated, not been swallowed")
    except ValueError:
        pass


def main() -> bool:
    tests = [test_connect_error_degrades_to_503, test_timeout_degrades_to_503,
              test_healthy_call_passes_through_unchanged, test_unrelated_exceptions_still_propagate]
    failed = []
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} pass")
    return not failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = main()
    print("✅ intelligence graceful degradation OK" if ok else "❌ FAILED")
    raise SystemExit(0 if ok else 1)
