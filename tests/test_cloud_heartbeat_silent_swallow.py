"""Regression for core/cloud/heartbeat.py's build_payload(): both except blocks
used the literal "[VECTOR] silent swallow" placeholder with no exception
variable at all -- the same systemic bug fixed 50+ times this cycle. A real
failure reading agent registry or episodic memory stats produced a log line
with zero diagnostic information.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.cloud.heartbeat import CloudBrainHeartbeat


def test_build_payload_logs_real_exception_on_agent_registry_failure():
    hb = CloudBrainHeartbeat(brain_url="https://example.invalid")
    with patch("core.city.agent_registry.AgentRegistry") as MockRegistry, \
         patch("core.cloud.heartbeat.logger") as mock_logger:
        MockRegistry.side_effect = RuntimeError("registry boom")
        payload = hb.build_payload()
    assert "alive_agents" not in payload
    assert mock_logger.warning.called
    call_text = str(mock_logger.warning.call_args)
    assert "silent swallow" not in call_text
    assert "registry boom" in call_text


def test_build_payload_logs_real_exception_on_episodic_failure():
    hb = CloudBrainHeartbeat(brain_url="https://example.invalid")
    with patch("core.memory.episodic.EpisodicMemory") as MockMem, \
         patch("core.cloud.heartbeat.logger") as mock_logger:
        MockMem.side_effect = RuntimeError("episodic boom")
        payload = hb.build_payload()
    assert "memory_events" not in payload
    assert mock_logger.warning.called
    call_text = str(mock_logger.warning.call_args)
    assert "silent swallow" not in call_text
    assert "episodic boom" in call_text


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
