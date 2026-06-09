"""Test package compatibility aliases for finagent_core.

These tests historically used relative imports as if implementation modules
were nested under tests/. Keep that import contract stable while running from
the monorepo root.
"""

from __future__ import annotations

import importlib
import sys


_PACKAGE = __name__.rsplit(".tests", 1)[0]
sys.modules.setdefault("finagent_core", importlib.import_module(_PACKAGE))

for _name in ("core_agent", "persona_registry", "persona_runtime", "resources", "modules"):
    _module = importlib.import_module(f"{_PACKAGE}.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    sys.modules.setdefault(f"finagent_core.{_name}", _module)
