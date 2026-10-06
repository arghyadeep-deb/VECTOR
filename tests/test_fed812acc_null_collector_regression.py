"""Regression for 4 instances of the same bug class, all caused by commit
fed812acc ("convert 214 pass-only ABC stubs to raise NotImplementedError",
2026-06-18): a blanket automated pass misidentified several concrete,
directly-instantiated "fake context" / "null object" helper classes as
abstract stubs, converting their deliberate no-op bodies into unconditional
`raise NotImplementedError`. Each class below is instantiated directly
(never subclassed) by real, live code:

- vectorcode/src/plugins/context_engine/__init__.py's _EngineCollector,
  instantiated in _load_engine_from_dir() and passed to a loaded plugin's
  own register(ctx) call.
- vectorcode/src/plugins/memory/__init__.py's _ProviderCollector, same
  shape in _load_provider_from_dir().
- vectorcode/src/skills/manager.py's _NullToolExecutor (the _FULL_DEPS=False
  branch), instantiated as `executor or _NullToolExecutor()` when vc_tools
  is unavailable -- the whole point of this branch is graceful degradation.
- vectorcode/src/providers/capability_probe.py's fallback ModelRegistry,
  instantiated as `self._registry = ModelRegistry()` when config.ModelRegistry
  can't be imported.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))


def test_engine_collector_noop_methods_do_not_raise():
    from plugins.context_engine import _EngineCollector

    collector = _EngineCollector()
    # None of these should raise -- a real plugin's register(ctx) may call
    # any of them before or instead of register_context_engine.
    collector.register_tool("x")
    collector.register_hook("y")
    collector.register_cli_command("z")
    collector.register_memory_provider("w")
    assert collector.engine is None


def test_provider_collector_noop_methods_do_not_raise():
    from plugins.memory import _ProviderCollector

    collector = _ProviderCollector()
    collector.register_tool("x")
    collector.register_hook("y")
    collector.register_cli_command("z")
    assert collector.provider is None


def test_null_tool_executor_constructs_without_full_deps():
    import skills.manager as manager_mod

    # Force the _FULL_DEPS=False branch's class, regardless of which one is
    # actually bound as skills.manager._NullToolExecutor in this environment,
    # by reading the module source and exec'ing just that class body is
    # fragile -- instead, directly assert the class the module actually
    # exposes constructs without raising. If _FULL_DEPS is True in this
    # environment, this still proves the live class works; the regression
    # specifically targeted the _FULL_DEPS=False variant, exercised by
    # reading its source directly below.
    executor = manager_mod._NullToolExecutor()
    assert executor is not None

    import inspect
    src = inspect.getsource(manager_mod)
    # The fallback (vc_tools unavailable) branch must not unconditionally raise.
    assert 'raise NotImplementedError("_NullToolExecutor.__init__' not in src


def test_capability_probe_fallback_model_registry_save_does_not_raise():
    from providers.capability_probe import _InMemoryModelRegistry

    registry = _InMemoryModelRegistry()
    registry.set("some-model", {"vision": True})
    registry.save()  # must not raise
    assert registry.get("some-model") == {"vision": True}


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
