"""Regression: vectorcode/src/vector_cli/gateway_cmd.py's `gateway start`
(no --install) printed "Gateway started. Press Ctrl+C to stop." without
ever starting anything -- no subprocess call, no blocking loop, no real
action at all (phantom success). Dormant today (this click group is not
registered anywhere in the real CLI), fixed anyway per this cycle's bar.
"""
import sys
from pathlib import Path

from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vector_cli.gateway_cmd import start


def test_foreground_start_does_not_claim_success():
    runner = CliRunner()
    result = runner.invoke(start, [])
    assert result.exit_code != 0
    assert "Gateway started" not in result.output
    assert "not implemented" in result.output


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
