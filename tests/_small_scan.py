"""Shared autouse fixture: the REAL ArchitectBot scan runs over a small project, not the whole repo.

`read_code` (a GREEN action several learning tests act on for real) runs ArchitectBot.scan_codebase_with_graph over the working directory.
Over the whole 7,000-file repo that takes ~26 s alone and passes the Governor's 45 s timeout under any load, so the reward the tests
assert (~0.63) turned into a failure reward and the test failed with machine load, not with code (r13 control_d 2026-09-27, r16 flagship
the same night). Import this fixture into a test module to apply it there:  from tests._small_scan import small_scan_root  # noqa: F401
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def small_scan_root(tmp_path_factory, monkeypatch):
    from districts.coding.architect_bot import ArchitectBot

    proj = tmp_path_factory.mktemp("small_scan_project")
    (proj / "__init__.py").write_text("")
    (proj / "sample.py").write_text("class A:" + chr(10) + "    def f(self):" + chr(10) + "        return 1" + chr(10))
    for name in ("scan_codebase_with_graph", "scan_codebase"):
        original = getattr(ArchitectBot, name)

        def redirect(self, root=".", *a, _orig=original, **k):
            return _orig(self, str(proj) if root in (".", "", None) else root, *a, **k)

        monkeypatch.setattr(ArchitectBot, name, redirect)
    yield
