"""Regression: vectorcode/src/acp/server.py's ACPServer defaulted to
host="0.0.0.0" -- binding all network interfaces by default on a server
with zero authentication on any of its 8 routes (/acp/run executes a real
AIAgent conversation). The real caller (cli.py's `vector acp serve`)
already passed an explicit 127.0.0.1 default at the argparse level, but
the class's own default was the unsafe one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.acp.server import ACPServer


def test_default_host_is_localhost():
    s = ACPServer()
    assert s.host == "127.0.0.1"


def test_explicit_host_override_still_works():
    s = ACPServer(host="0.0.0.0", port=9999)
    assert s.host == "0.0.0.0"
    assert s.port == 9999


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
