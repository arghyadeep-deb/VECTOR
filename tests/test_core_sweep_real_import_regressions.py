"""Regressions found by a real-import sweep of core/ and districts/ (Phase 3
whole-repo audit): a static ast.parse() check would have passed both of
these files, but a real `import` did not.

1. core/coding_assistant/core/programmatic.py's ClientMetadata -- an earlier
   blanket "pass-only stub -> raise NotImplementedError" automated commit
   (fed812acc) replaced a deliberate no-op telemetry stub's __init__ body
   with an unconditional `raise`, placed directly in the class body (not
   even inside __init__), so simply defining the class -- which happens at
   import time, before _DEFAULT_CLIENT_METADATA = ClientMetadata(...) a few
   lines later -- crashed the whole module. Confirmed via
   `git show fed812acc^:<path>` that the original was a real no-op
   `def __init__(self, name="", version=""): pass`.

2. core/mining/vllm_pearl.py imported `from core.mining._discovery import
   detect_for_engine_model` -- no such module exists (core/mining/discovery.py,
   no underscore, does). The function detect_for_engine_model is real and
   exists there. Fixed the import path.

   NOTE: vllm_pearl.py also does `from core.mining._docker import
   PearlDockerLauncher`, and core/mining/_docker.py has never existed in
   git history at all (confirmed: `git log --all --diff-filter=D` finds no
   deletion). The real PearlDockerLauncher class only exists in the
   parallel vectorcode/src/mining/_docker.py tree, which was apparently
   never ported to core/mining/ despite vllm_pearl.py itself having been.
   This is NOT fixed here -- porting a class across trees (or redesigning
   the import boundary) is a bigger, more interpretive change than this
   narrow-bug-fix pass covers; flagged in docs/OPEN_ISSUES.md for an owner
   decision instead. This test therefore checks the specific import this
   pass fixed (core.mining.discovery), not a full `import
   core.mining.vllm_pearl`, which still fails for the separate _docker
   reason.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_client_metadata_is_constructable():
    from core.coding_assistant.core.programmatic import ClientMetadata

    meta = ClientMetadata(name="vibe_programmatic", version="1.0")
    assert meta is not None


def test_programmatic_module_imports_successfully():
    # Importing the whole module exercises the exact failure: the class
    # body's bare raise executed at class-definition time, during this
    # module's own import, before anything else could run.
    import importlib

    import core.coding_assistant.core.programmatic as programmatic

    importlib.reload(programmatic)
    assert hasattr(programmatic, "_DEFAULT_CLIENT_METADATA")


def test_mining_discovery_import_path_is_correct():
    # core.mining._discovery does not exist; the real function lives in
    # core.mining.discovery (no underscore).
    from core.mining.discovery import detect_for_engine_model

    assert callable(detect_for_engine_model)


def test_vllm_pearl_no_longer_references_nonexistent_discovery_module():
    # Read the source directly rather than importing the module: it still
    # fails to import for the separate, unfixed core.mining._docker reason
    # documented above, which this test is not about.
    vllm_pearl_path = (
        Path(__file__).parent.parent / "core" / "mining" / "vllm_pearl.py"
    )
    src = vllm_pearl_path.read_text(encoding="utf-8")
    assert "from core.mining._discovery import" not in src
    assert "from core.mining.discovery import" in src


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
