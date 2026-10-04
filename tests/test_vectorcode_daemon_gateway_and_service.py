"""Regression for two bugs in vectorcode/src/daemon/:

- gateway.py: GatewayDaemon.session_key() unconditionally appended
  f":{thread_id}" even when thread_id is None, embedding the literal
  string "None" into the key instead of omitting the segment. The live
  canonical session-key builder (vectorcode/src/gateway/session.py)
  conditionally omits absent segments -- this reimplementation diverged
  from that pattern.

- service.py: core/loop/autonomous_loop.py does
  `from vectorcode.src.daemon.service import ServiceManager` and
  `self._daemon_mgr = ServiceManager()` inside a bare try/except --
  ServiceManager never existed in this file (confirmed: zero matches for
  "class ServiceManager" anywhere in the repo before this fix), so the
  import always raised ImportError and self._daemon_mgr was silently
  always None. Added a thin ServiceManager wrapping the two generator
  functions that already made up this module's entire capability.

Both dormant from GatewayDaemon's own perspective (zero real callers of
GatewayDaemon/session_key itself), but the ServiceManager import failure
is live code executed by core/loop/autonomous_loop.py on every autonomous
loop startup -- fixed anyway per this cycle's established bar, and noted
separately (OPEN_ISSUES.md) that self._daemon_mgr is never read anywhere
after assignment, so this wiring may still need owner follow-up.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.daemon.gateway import GatewayDaemon
from vectorcode.src.daemon.service import ServiceManager


def test_session_key_omits_thread_id_when_absent():
    key = GatewayDaemon.session_key("telegram", "dm", "12345", None)
    assert key == "agent:main:telegram:dm:12345"
    assert "None" not in key


def test_session_key_includes_thread_id_when_present():
    key = GatewayDaemon.session_key("telegram", "dm", "12345", "thread1")
    assert key == "agent:main:telegram:dm:12345:thread1"


def test_service_manager_importable_and_wraps_generators():
    sm = ServiceManager()
    systemd = sm.install_systemd()
    launchd = sm.install_launchd()
    assert "[Unit]" in systemd
    assert "<?xml" in launchd


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
