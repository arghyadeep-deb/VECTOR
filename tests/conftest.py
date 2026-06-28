from __future__ import annotations

import os
import sys
import asyncio
from pathlib import Path


# Windows: force the SelectorEventLoop for the entire test session.
# The default ProactorEventLoop allocates an IOCP self-pipe socketpair per event
# loop. A large suite calls asyncio.run() thousands of times; the accumulated
# socketpairs exhaust Windows socket buffers (WinError 10055) and a later loop
# hangs forever inside GetQueuedCompletionStatus — which then cascades into
# spurious ERRORs on every downstream async/DB test. Every asyncio subprocess
# call in this suite is mocked (AsyncMock), so SelectorEventLoop is safe here.
# (test_collections.py set this locally and claimed it "mirrors conftest.py";
# this is the global definition that claim referred to.)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_TEST_DATA_DIR = Path(__file__).resolve().parents[1] / "test_tmp" / "vector_pytest_data"
_TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("VECTOR_TEST_DATA_DIR", str(_TEST_DATA_DIR))
