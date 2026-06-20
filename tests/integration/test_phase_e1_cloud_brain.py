"""E1 tests — cloud brain wiring: config and heartbeat.

The cloud brain runs entirely on the Cloudflare Worker (api/) — see
api/src/router.ts. The original Fly.io brain_server has been removed
(superseded; see cloud/_deprecated_brain_server_fly/ if it still exists).
These tests cover what's still real: CONFIG["cloud"] wiring, the generic
CloudBrainHeartbeat poster used by run_vector.py, and that run_vector.py
actually starts it. No live network calls.
"""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path


_CORE_CLOUD = Path(__file__).parent.parent.parent / "core" / "cloud"
_ROOT = Path(__file__).parent.parent.parent


# ── CONFIG["cloud"] wiring ────────────────────────────────────────────────────


class TestCloudConfig(unittest.TestCase):
    """CONFIG["cloud"] dict is wired with brain_url and api_key keys."""

    def test_config_has_cloud_key(self):
        from core.config import CONFIG
        self.assertIn("cloud", CONFIG)

    def test_cloud_has_brain_url_key(self):
        from core.config import CONFIG
        self.assertIn("brain_url", CONFIG["cloud"])

    def test_cloud_brain_url_is_string(self):
        from core.config import CONFIG
        self.assertIsInstance(CONFIG["cloud"]["brain_url"], str)

    def test_cloud_has_api_key(self):
        from core.config import CONFIG
        self.assertIn("api_key", CONFIG["cloud"])

    def test_cloud_brain_url_empty_by_default(self):
        """Without VECTOR_BRAIN_URL env var, brain_url should be empty."""
        import os
        from core.config import CONFIG
        if not os.environ.get("VECTOR_BRAIN_URL"):
            self.assertEqual(CONFIG["cloud"]["brain_url"], "")


# ── CloudBrainHeartbeat ───────────────────────────────────────────────────────


class TestCloudBrainHeartbeat(unittest.TestCase):
    """core/cloud/heartbeat.py CloudBrainHeartbeat class — no live network calls."""

    def test_heartbeat_module_importable(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        self.assertIsNotNone(CloudBrainHeartbeat)

    def test_heartbeat_disabled_with_no_url(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="", api_key="")
        self.assertFalse(hb.is_enabled())

    def test_heartbeat_enabled_with_url_and_httpx(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat, _HTTPX_OK
        hb = CloudBrainHeartbeat(brain_url="https://vector-api.example.workers.dev", api_key="test")
        # enabled iff httpx is importable
        self.assertEqual(hb.is_enabled(), _HTTPX_OK)

    def test_heartbeat_payload_has_ts(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-api.example.workers.dev")
        payload = hb.build_payload()
        self.assertIn("ts", payload)

    def test_heartbeat_payload_ts_is_float(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-api.example.workers.dev")
        self.assertIsInstance(hb.build_payload()["ts"], float)

    def test_heartbeat_payload_has_source(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-api.example.workers.dev")
        self.assertIn("source", hb.build_payload())

    def test_heartbeat_payload_source_is_string(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-api.example.workers.dev")
        self.assertIsInstance(hb.build_payload()["source"], str)

    def test_heartbeat_stop_clears_running_flag(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-api.example.workers.dev")
        hb._running = True
        hb.stop()
        self.assertFalse(hb._running)

    def test_heartbeat_send_returns_false_when_disabled(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="")
        result = asyncio.run(hb.send())
        self.assertFalse(result)

    def test_headers_include_bearer_when_key_set(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-api.example.workers.dev", api_key="secret123")
        headers = hb._headers()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))

    def test_headers_no_auth_when_no_key(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-api.example.workers.dev", api_key="")
        headers = hb._headers()
        self.assertNotIn("Authorization", headers)


# ── run_vector.py cloud integration ──────────────────────────────────────────


class TestRunVectorCloudIntegration(unittest.TestCase):
    """run_vector.py wires CloudBrainHeartbeat in _start_background_services."""

    def _src(self) -> str:
        return (_ROOT / "run_vector.py").read_text(encoding="utf-8")

    def test_run_vector_imports_cloud_heartbeat(self):
        self.assertIn("CloudBrainHeartbeat", self._src())

    def test_run_vector_references_brain_url(self):
        self.assertIn("brain_url", self._src())

    def test_run_vector_starts_heartbeat_task(self):
        self.assertIn("start_loop", self._src())

    def test_core_cloud_directory_exists(self):
        self.assertTrue(_CORE_CLOUD.exists())

    def test_core_cloud_init_exists(self):
        self.assertTrue((_CORE_CLOUD / "__init__.py").exists())

    def test_core_cloud_heartbeat_file_exists(self):
        self.assertTrue((_CORE_CLOUD / "heartbeat.py").exists())


if __name__ == "__main__":
    unittest.main()
