"""Integration tests — Session B3: Multi-modal context (camera + screen) → context_engine."""
from __future__ import annotations

import asyncio
import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestSensingConfigDefaults(unittest.TestCase):
    """SensingConfig has screen_enabled and camera_enabled, both default False."""

    def test_screen_enabled_exists(self):
        from core.config import CONFIG
        sensing = CONFIG.get("sensing", {})
        self.assertIn("screen_enabled", sensing)

    def test_camera_enabled_exists(self):
        from core.config import CONFIG
        sensing = CONFIG.get("sensing", {})
        self.assertIn("camera_enabled", sensing)

    def test_screen_enabled_default_false(self):
        from core.config import CONFIG
        self.assertFalse(CONFIG.get("sensing", {}).get("screen_enabled"))

    def test_camera_enabled_default_false(self):
        from core.config import CONFIG
        self.assertFalse(CONFIG.get("sensing", {}).get("camera_enabled"))

    def test_sensing_config_class_has_fields(self):
        from core.config import SensingConfig
        fields = SensingConfig.model_fields
        self.assertIn("screen_enabled", fields)
        self.assertIn("camera_enabled", fields)


class TestSenseCacheModule(unittest.TestCase):
    """update_sense_cache() and _SENSE_CACHE work correctly."""

    def setUp(self):
        from core.loop.context_engine import _SENSE_CACHE
        self._orig_screen = _SENSE_CACHE.get("screen_summary", "")
        self._orig_presence = _SENSE_CACHE.get("presence", "unknown")

    def tearDown(self):
        from core.loop.context_engine import update_sense_cache
        update_sense_cache(self._orig_screen, self._orig_presence)

    def test_update_sense_cache_exists(self):
        from core.loop.context_engine import update_sense_cache
        self.assertTrue(callable(update_sense_cache))

    def test_sense_cache_dict_exists(self):
        from core.loop.context_engine import _SENSE_CACHE
        self.assertIsInstance(_SENSE_CACHE, dict)

    def test_update_sets_screen_summary(self):
        from core.loop.context_engine import update_sense_cache, _SENSE_CACHE
        update_sense_cache(screen_summary="vim editor open", presence="present")
        self.assertEqual(_SENSE_CACHE["screen_summary"], "vim editor open")

    def test_update_sets_presence(self):
        from core.loop.context_engine import update_sense_cache, _SENSE_CACHE
        update_sense_cache(screen_summary="", presence="multiple")
        self.assertEqual(_SENSE_CACHE["presence"], "multiple")

    def test_screen_summary_truncated_to_300(self):
        from core.loop.context_engine import update_sense_cache, _SENSE_CACHE
        long_summary = "x" * 500
        update_sense_cache(screen_summary=long_summary)
        self.assertLessEqual(len(_SENSE_CACHE["screen_summary"]), 300)

    def test_empty_presence_defaults_to_unknown(self):
        from core.loop.context_engine import update_sense_cache, _SENSE_CACHE
        update_sense_cache(screen_summary="", presence="")
        self.assertEqual(_SENSE_CACHE["presence"], "unknown")


class TestContextEngineIncludesScreenSummary(unittest.TestCase):
    """session_hydration_prompt() includes screen_summary and presence when set."""

    def setUp(self):
        from core.loop.context_engine import update_sense_cache
        self._restore = ("", "unknown")
        update_sense_cache("", "unknown")

    def tearDown(self):
        from core.loop.context_engine import update_sense_cache
        update_sense_cache(*self._restore)

    def test_screen_summary_in_hydration_when_set(self):
        from core.loop.context_engine import update_sense_cache, ContextEngine
        update_sense_cache(screen_summary="def main(): print('hello')", presence="present")
        ce = ContextEngine()
        prompt = ce.session_hydration_prompt()
        self.assertIn("Screen:", prompt)

    def test_presence_in_hydration_when_set(self):
        from core.loop.context_engine import update_sense_cache, ContextEngine
        update_sense_cache(screen_summary="", presence="absent")
        ce = ContextEngine()
        prompt = ce.session_hydration_prompt()
        self.assertIn("Presence:", prompt)

    def test_empty_screen_summary_not_in_hydration(self):
        from core.loop.context_engine import update_sense_cache, ContextEngine
        update_sense_cache(screen_summary="", presence="unknown")
        ce = ContextEngine()
        prompt = ce.session_hydration_prompt()
        self.assertNotIn("Screen:", prompt)

    def test_unknown_presence_not_in_hydration(self):
        from core.loop.context_engine import update_sense_cache, ContextEngine
        update_sense_cache(screen_summary="", presence="unknown")
        ce = ContextEngine()
        prompt = ce.session_hydration_prompt()
        self.assertNotIn("Presence:", prompt)

    def test_get_world_state_has_screen_summary_key(self):
        from core.loop.context_engine import ContextEngine
        ce = ContextEngine()
        ws = ce.get_world_state()
        self.assertIn("screen_summary", ws)

    def test_get_world_state_has_presence_key(self):
        from core.loop.context_engine import ContextEngine
        ce = ContextEngine()
        ws = ce.get_world_state()
        self.assertIn("presence", ws)

    def test_presence_value_from_cache_in_world_state(self):
        from core.loop.context_engine import update_sense_cache, ContextEngine
        update_sense_cache(screen_summary="test", presence="multiple")
        ws = ContextEngine().get_world_state()
        self.assertEqual(ws["presence"], "multiple")


class TestSenseTickDisabledByDefault(unittest.TestCase):
    """_sense_tick() is a no-op when sensing is disabled (default)."""

    def test_sense_tick_is_coroutine(self):
        from core.loop.autonomous_loop import AutonomousLoop
        al = AutonomousLoop.__new__(AutonomousLoop)
        self.assertTrue(inspect.iscoroutinefunction(al._sense_tick))

    def test_sense_tick_noop_when_disabled(self):
        from core.loop.autonomous_loop import AutonomousLoop
        from core.loop.context_engine import _SENSE_CACHE, update_sense_cache

        update_sense_cache("", "unknown")
        before_screen = _SENSE_CACHE["screen_summary"]
        before_presence = _SENSE_CACHE["presence"]

        async def _run():
            al = AutonomousLoop.__new__(AutonomousLoop)
            with patch("core.config.CONFIG") as mock_cfg:
                mock_cfg.get = MagicMock(return_value={"screen_enabled": False, "camera_enabled": False})
                await al._sense_tick()

        asyncio.run(_run())
        self.assertEqual(_SENSE_CACHE["screen_summary"], before_screen)
        self.assertEqual(_SENSE_CACHE["presence"], before_presence)

    def test_sense_loop_is_coroutine(self):
        from core.loop.autonomous_loop import AutonomousLoop
        al = AutonomousLoop.__new__(AutonomousLoop)
        self.assertTrue(inspect.iscoroutinefunction(al.sense_loop))

    def test_sense_loop_in_run_forever_source(self):
        from core.loop.autonomous_loop import AutonomousLoop
        src = inspect.getsource(AutonomousLoop.run_forever)
        self.assertIn("sense_loop", src)


class TestSenseTickScreenEnabled(unittest.TestCase):
    """_sense_tick() calls ScreenObserver and updates sense cache when screen_enabled."""

    def setUp(self):
        from core.loop.context_engine import update_sense_cache
        update_sense_cache("", "unknown")

    def tearDown(self):
        from core.loop.context_engine import update_sense_cache
        update_sense_cache("", "unknown")

    def test_screen_summary_updated_when_screen_enabled(self):
        from core.loop.autonomous_loop import AutonomousLoop
        from core.loop.context_engine import _SENSE_CACHE

        mock_observe_result = {
            "activity": "coding",
            "text_snippet": "def hello_world():",
            "timestamp": "2026-01-01T00:00:00Z",
        }

        async def _run():
            al = AutonomousLoop.__new__(AutonomousLoop)
            al._running = True
            with patch("core.config.CONFIG") as mock_cfg:
                mock_cfg.get = MagicMock(side_effect=lambda k, d=None: {
                    "sensing": {"screen_enabled": True, "camera_enabled": False}
                }.get(k, d))
                with patch("core.sensing.screen_observer.ScreenObserver") as mock_so:
                    mock_so.return_value.observe.return_value = mock_observe_result
                    await al._sense_tick()

        asyncio.run(_run())

    def test_presence_updated_when_camera_enabled_owner_present(self):
        from core.loop.autonomous_loop import AutonomousLoop
        from core.loop.context_engine import _SENSE_CACHE

        async def _run():
            al = AutonomousLoop.__new__(AutonomousLoop)
            al._running = True
            with patch("core.config.CONFIG") as mock_cfg:
                mock_cfg.get = MagicMock(side_effect=lambda k, d=None: {
                    "sensing": {"screen_enabled": False, "camera_enabled": True}
                }.get(k, d))
                with patch("core.sensing.camera.FaceDetector") as mock_fd:
                    mock_fd.return_value.capture_and_scan.return_value = [
                        {"name": "Arghyadeep", "confidence": 0.95, "bbox": (0, 0, 0, 0)}
                    ]
                    await al._sense_tick()

        asyncio.run(_run())

    def test_presence_absent_when_no_faces(self):
        from core.loop.autonomous_loop import AutonomousLoop
        from core.loop.context_engine import _SENSE_CACHE, update_sense_cache

        async def _run():
            al = AutonomousLoop.__new__(AutonomousLoop)
            al._running = True
            mock_cfg = MagicMock()
            mock_cfg.get = MagicMock(side_effect=lambda k, d=None: {
                "sensing": {"screen_enabled": False, "camera_enabled": True}
            }.get(k, d))
            with patch("core.loop.autonomous_loop.CONFIG", mock_cfg):
                with patch("core.sensing.camera.FaceDetector") as mock_fd:
                    mock_fd.return_value.capture_and_scan.return_value = []
                    await al._sense_tick()
                    return _SENSE_CACHE["presence"]

        result = asyncio.run(_run())
        self.assertEqual(result, "absent")

    def test_presence_multiple_when_multiple_faces(self):
        from core.loop.autonomous_loop import AutonomousLoop
        from core.loop.context_engine import _SENSE_CACHE

        async def _run():
            al = AutonomousLoop.__new__(AutonomousLoop)
            al._running = True
            mock_cfg = MagicMock()
            mock_cfg.get = MagicMock(side_effect=lambda k, d=None: {
                "sensing": {"screen_enabled": False, "camera_enabled": True}
            }.get(k, d))
            with patch("core.loop.autonomous_loop.CONFIG", mock_cfg):
                with patch("core.sensing.camera.FaceDetector") as mock_fd:
                    mock_fd.return_value.capture_and_scan.return_value = [
                        {"name": "Arghyadeep", "confidence": 0.9, "bbox": (0, 0, 0, 0)},
                        {"name": "unknown", "confidence": 0.0, "bbox": (0, 0, 0, 0)},
                    ]
                    await al._sense_tick()
                    return _SENSE_CACHE["presence"]

        result = asyncio.run(_run())
        self.assertEqual(result, "multiple")


class TestSenseTickErrorResistance(unittest.TestCase):
    """_sense_tick() never raises even when camera/screen fail."""

    def test_sense_tick_survives_screen_observer_error(self):
        from core.loop.autonomous_loop import AutonomousLoop

        async def _run():
            al = AutonomousLoop.__new__(AutonomousLoop)
            with patch("core.config.CONFIG") as mock_cfg:
                mock_cfg.get = MagicMock(side_effect=lambda k, d=None: {
                    "sensing": {"screen_enabled": True, "camera_enabled": False}
                }.get(k, d))
                with patch("core.sensing.screen_observer.ScreenObserver") as mock_so:
                    mock_so.return_value.observe.side_effect = RuntimeError("mss not available")
                    try:
                        await al._sense_tick()
                    except Exception as e:
                        self.fail(f"_sense_tick raised: {e}")

        asyncio.run(_run())

    def test_sense_tick_survives_camera_error(self):
        from core.loop.autonomous_loop import AutonomousLoop

        async def _run():
            al = AutonomousLoop.__new__(AutonomousLoop)
            with patch("core.config.CONFIG") as mock_cfg:
                mock_cfg.get = MagicMock(side_effect=lambda k, d=None: {
                    "sensing": {"screen_enabled": False, "camera_enabled": True}
                }.get(k, d))
                with patch("core.sensing.camera.FaceDetector") as mock_fd:
                    mock_fd.return_value.capture_and_scan.side_effect = RuntimeError("no camera")
                    try:
                        await al._sense_tick()
                    except Exception as e:
                        self.fail(f"_sense_tick raised: {e}")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
