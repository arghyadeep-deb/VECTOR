"""E1 tests — Fly.io brain server wiring: config, heartbeat, server structure.

All tests here verify LOCAL wiring only — no live network calls, no fly CLI.
The deployment step (fly launch + fly deploy) is run separately after confirmation.
"""
from __future__ import annotations

import asyncio
import importlib.util
import unittest
from pathlib import Path


_CLOUD_DIR = Path(__file__).parent.parent.parent / "cloud" / "brain_server"
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


# ── cloud/brain_server/vector_config.py ───────────────────────────────────────


class TestStandaloneConfig(unittest.TestCase):
    """cloud/brain_server/vector_config.py is a self-contained CONFIG fallback."""

    def _load(self):
        spec = importlib.util.spec_from_file_location(
            "vector_config_e1", _CLOUD_DIR / "vector_config.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_vector_config_exists(self):
        self.assertTrue((_CLOUD_DIR / "vector_config.py").exists())

    def test_standalone_config_has_system_name(self):
        self.assertIn("system_name", self._load().CONFIG)

    def test_standalone_config_has_version(self):
        self.assertIn("version", self._load().CONFIG)

    def test_standalone_config_has_env(self):
        self.assertIn("env", self._load().CONFIG)

    def test_standalone_config_has_allowed_origins(self):
        self.assertIn("allowed_origins", self._load().CONFIG)

    def test_standalone_config_allowed_origins_is_list(self):
        cfg = self._load().CONFIG
        self.assertIsInstance(cfg["allowed_origins"], list)


# ── fly.toml structure ────────────────────────────────────────────────────────


class TestFlyToml(unittest.TestCase):
    """cloud/brain_server/fly.toml is correctly configured for Fly.io."""

    def _content(self) -> str:
        return (_CLOUD_DIR / "fly.toml").read_text(encoding="utf-8")

    def test_fly_toml_exists(self):
        self.assertTrue((_CLOUD_DIR / "fly.toml").exists())

    def test_fly_toml_app_name_vector_brain(self):
        self.assertIn('app = "vector-brain"', self._content())

    def test_fly_toml_internal_port_8000(self):
        self.assertIn("internal_port = 8000", self._content())

    def test_fly_toml_health_check_path(self):
        self.assertIn('path = "/health"', self._content())

    def test_fly_toml_force_https(self):
        self.assertIn("force_https = true", self._content())

    def test_fly_toml_references_dockerfile(self):
        self.assertIn("Dockerfile", self._content())


# ── Dockerfile structure ──────────────────────────────────────────────────────


class TestDockerfile(unittest.TestCase):
    """cloud/brain_server/Dockerfile is valid for cloud deployment."""

    def _content(self) -> str:
        return (_CLOUD_DIR / "Dockerfile").read_text(encoding="utf-8")

    def test_dockerfile_exists(self):
        self.assertTrue((_CLOUD_DIR / "Dockerfile").exists())

    def test_dockerfile_runs_main_py(self):
        self.assertIn("main.py", self._content())

    def test_dockerfile_uses_python311(self):
        self.assertIn("python:3.11", self._content())

    def test_dockerfile_exposes_8000(self):
        self.assertIn("8000", self._content())


# ── brain_server/main.py structure ───────────────────────────────────────────


class TestBrainServerMain(unittest.TestCase):
    """cloud/brain_server/main.py has required endpoints and auth."""

    def _src(self) -> str:
        return (_CLOUD_DIR / "main.py").read_text(encoding="utf-8")

    def test_main_py_exists(self):
        self.assertTrue((_CLOUD_DIR / "main.py").exists())

    def test_has_status_endpoint(self):
        self.assertIn('@app.get("/status")', self._src())

    def test_has_health_endpoint(self):
        self.assertIn('@app.get("/health")', self._src())

    def test_has_heartbeat_receive_endpoint(self):
        self.assertIn("/heartbeat", self._src())

    def test_has_auth_middleware(self):
        self.assertIn("_auth_middleware", self._src())

    def test_api_key_read_from_env_not_hardcoded(self):
        src = self._src()
        self.assertIn('os.environ.get("VECTOR_API_KEY"', src)

    def test_config_import_has_fallback(self):
        src = self._src()
        self.assertIn("vector_config", src)

    def test_requirements_has_fastapi(self):
        req = (_CLOUD_DIR / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("fastapi", req)

    def test_requirements_has_uvicorn(self):
        req = (_CLOUD_DIR / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("uvicorn", req)

    def test_requirements_has_httpx(self):
        req = (_CLOUD_DIR / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("httpx", req)


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
        hb = CloudBrainHeartbeat(brain_url="https://vector-brain.fly.dev", api_key="test")
        # enabled iff httpx is importable
        self.assertEqual(hb.is_enabled(), _HTTPX_OK)

    def test_heartbeat_payload_has_ts(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-brain.fly.dev")
        payload = hb.build_payload()
        self.assertIn("ts", payload)

    def test_heartbeat_payload_ts_is_float(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-brain.fly.dev")
        self.assertIsInstance(hb.build_payload()["ts"], float)

    def test_heartbeat_payload_has_source(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-brain.fly.dev")
        self.assertIn("source", hb.build_payload())

    def test_heartbeat_payload_source_is_string(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-brain.fly.dev")
        self.assertIsInstance(hb.build_payload()["source"], str)

    def test_heartbeat_stop_clears_running_flag(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-brain.fly.dev")
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
        hb = CloudBrainHeartbeat(brain_url="https://vector-brain.fly.dev", api_key="secret123")
        headers = hb._headers()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer "))

    def test_headers_no_auth_when_no_key(self):
        from core.cloud.heartbeat import CloudBrainHeartbeat
        hb = CloudBrainHeartbeat(brain_url="https://vector-brain.fly.dev", api_key="")
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
