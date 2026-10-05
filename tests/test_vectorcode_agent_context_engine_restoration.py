"""Regression for a catastrophic import-chain break in vectorcode/src/agent/.

An earlier blanket automated commit (fed812acc, "convert 214 pass-only ABC
stubs to raise NotImplementedError") deleted vectorcode/src/agent/
context_engine.py entirely -- it mistook the whole abstract-base-class
module (ContextEngine, an ABC with both @abstractmethod stubs and real
default-implementation methods) for dead stub code.

This broke context_compressor.py's `from agent.context_engine import
ContextEngine` at module level, which in turn broke run_agent.py's own
module-level `from agent.context_compressor import ContextCompressor` --
meaning the primary agent entry point could not be imported at all.

The pre-existing "regression test" for context_compressor.py
(test_vectorcode_agent_context_compressor_logging.py) only ever did a
static ast.parse() of the source text and never attempted a real import,
so this had gone completely undetected since the deleting commit.

Restored agent/context_engine.py from git history (fed812acc^) byte-for-
byte. This test proves the real import now succeeds, not just that the
source text parses.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))


def test_context_engine_imports_and_is_abstract():
    from agent.context_engine import ContextEngine
    import pytest

    with pytest.raises(TypeError):
        ContextEngine()  # abstract -- must not be directly instantiable


def test_context_compressor_imports_and_subclasses_context_engine():
    from agent.context_engine import ContextEngine
    from agent.context_compressor import ContextCompressor

    assert issubclass(ContextCompressor, ContextEngine)


def test_context_compressor_instantiates_and_satisfies_abc_contract():
    from agent.context_compressor import ContextCompressor

    cc = ContextCompressor(model="gpt-4o-mini", quiet_mode=True)
    assert cc.name == "compressor"
    assert isinstance(cc.context_length, int)
    assert callable(cc.compress)
    assert callable(cc.should_compress)


def test_run_agent_module_imports_without_raising():
    """The actual regression: run_agent.py has an unguarded, module-level
    `from agent.context_compressor import ContextCompressor` -- if that
    chain is broken, the entire primary agent entry point cannot be
    imported. This must succeed."""
    import run_agent  # noqa: F401 -- import success is the assertion


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
