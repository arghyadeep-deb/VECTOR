"""Regression for vectorcode/src/vc_tools/browser.py's BrowserNavigateTool:

if vectorcode.src.vc_security.ssrf fails to import for any reason (not
just "module genuinely absent" -- any transitive ImportError), the SSRF
check used to be skipped via a bare `except ImportError: pass`, silently
disabling protection against navigating this headless browser tool to
internal network addresses or cloud metadata endpoints (169.254.169.254
etc.) with zero diagnostic. Fixed to log a loud warning naming the exact
URL that was navigated to with no SSRF protection, so a broken guard
module is visible instead of a silent security regression.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import builtins

from vectorcode.src.vc_tools import browser as browser_module


def test_ssrf_import_failure_is_logged_not_silent(monkeypatch, caplog):
    import loguru

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if name == "vectorcode.src.vc_security.ssrf" or name.endswith("vc_security.ssrf"):
            raise ImportError("simulated: ssrf guard module unavailable")
        return real_import(name, *args, **kwargs)

    captured = []
    sink_id = loguru.logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
    monkeypatch.setattr(builtins, "__import__", _blocking_import)

    # _session.page requires playwright; monkeypatch it out so we can test
    # purely the SSRF-check branch without needing a real browser install.
    class _FakePage:
        def goto(self, *a, **kw):
            class _Resp:
                status = 200
            return _Resp()

        def title(self):
            return "stub"

        def inner_text(self, _sel):
            return ""

    monkeypatch.setattr(browser_module._session, "_page", _FakePage())

    try:
        tool = browser_module.BrowserNavigateTool()
        result = tool.execute(url="http://169.254.169.254/latest/meta-data/")
    finally:
        loguru.logger.remove(sink_id)
        monkeypatch.setattr(builtins, "__import__", real_import)

    assert result.success is True
    joined = "\n".join(captured)
    assert "SSRF guard unavailable" in joined
    assert "169.254.169.254" in joined


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
