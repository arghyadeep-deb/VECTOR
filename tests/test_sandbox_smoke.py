"""Smoke test for VectorSandbox — verifies subprocess isolation works."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.sandbox import get_sandbox, SandboxConfig


async def main():
    sb = get_sandbox(SandboxConfig(timeout_secs=10))

    # Test 1: basic arithmetic
    r = await sb.run_code_safe("print(2 + 2)")
    assert r.success, f"Test 1 failed: {r.stderr}"
    assert r.output.strip() == "4", f"Test 1 wrong output: {r.output!r}"
    print(f"Test 1 OK: 2+2 = {r.output.strip()}")

    # Test 2: multi-line code
    r = await sb.run_code_safe("x = 42\nprint(f'answer is {x}')")
    assert r.success, f"Test 2 failed: {r.stderr}"
    assert "42" in r.output, f"Test 2 wrong output: {r.output!r}"
    print(f"Test 2 OK: {r.output.strip()}")

    # Test 3: timeout kills runaway code
    r = await sb.run_code_safe("while True: pass", timeout=2)
    assert r.timed_out, "Test 3 should have timed out"
    assert not r.success, "Test 3 should not succeed"
    print(f"Test 3 OK: timed_out={r.timed_out}")

    # Test 4: error handling
    r = await sb.run_code_safe("raise ValueError('test error')")
    assert not r.success, "Test 4 should fail"
    assert "ValueError" in r.stderr or "ValueError" in r.output, f"Test 4 wrong error: {r.stderr!r}"
    print(f"Test 4 OK: caught ValueError")

    print("\nAll sandbox tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
