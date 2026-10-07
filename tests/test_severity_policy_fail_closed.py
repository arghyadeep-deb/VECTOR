"""Regression test for OD-52's unknown-severity fail-closed policy."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vc_security.severity_policy import SeverityPolicy
from vectorcode.src.vc_security.types import ThreatLevel


def test_missing_threat_level_fails_closed() -> None:
    policy = SeverityPolicy()
    policy._actions.pop(ThreatLevel.HIGH)

    assert policy.action_for(ThreatLevel.HIGH) == "block"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
