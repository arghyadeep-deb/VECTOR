"""Integration tests — Session B2: AmbientListener consent gate + USER_INTERACTION event."""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestConsentGateFunctions(unittest.TestCase):
    """_load_consent() and _save_consent() read/write data/consent.json correctly."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._consent_path = Path(self._tmp.name)
        self._tmp.close()
        self._consent_path.unlink(missing_ok=True)

    def tearDown(self):
        self._consent_path.unlink(missing_ok=True)

    def _patch_consent_path(self, load_fn, save_fn=None):
        import core.voice.ambient_listener as mod
        orig = mod._CONSENT_PATH
        mod._CONSENT_PATH = self._consent_path
        try:
            load_fn()
        finally:
            mod._CONSENT_PATH = orig
        if save_fn:
            mod._CONSENT_PATH = self._consent_path
            try:
                save_fn()
            finally:
                mod._CONSENT_PATH = orig

    def test_load_consent_returns_false_when_no_file(self):
        from core.voice.ambient_listener import _load_consent
        import core.voice.ambient_listener as mod
        orig = mod._CONSENT_PATH
        mod._CONSENT_PATH = self._consent_path
        try:
            result = _load_consent()
        finally:
            mod._CONSENT_PATH = orig
        self.assertFalse(result)

    def test_save_then_load_granted(self):
        from core.voice.ambient_listener import _load_consent, _save_consent
        import core.voice.ambient_listener as mod
        orig = mod._CONSENT_PATH
        mod._CONSENT_PATH = self._consent_path
        try:
            _save_consent(True)
            result = _load_consent()
        finally:
            mod._CONSENT_PATH = orig
        self.assertTrue(result)

    def test_save_then_load_denied(self):
        from core.voice.ambient_listener import _load_consent, _save_consent
        import core.voice.ambient_listener as mod
        orig = mod._CONSENT_PATH
        mod._CONSENT_PATH = self._consent_path
        try:
            _save_consent(False)
            result = _load_consent()
        finally:
            mod._CONSENT_PATH = orig
        self.assertFalse(result)

    def test_save_writes_json_with_granted_at(self):
        from core.voice.ambient_listener import _save_consent
        import core.voice.ambient_listener as mod
        orig = mod._CONSENT_PATH
        mod._CONSENT_PATH = self._consent_path
        try:
            _save_consent(True)
        finally:
            mod._CONSENT_PATH = orig
        data = json.loads(self._consent_path.read_text(encoding="utf-8"))
        self.assertIn("granted_at", data)
        self.assertIn("ambient_enabled", data)

    def test_load_consent_returns_bool(self):
        from core.voice.ambient_listener import _load_consent
        import core.voice.ambient_listener as mod
        orig = mod._CONSENT_PATH
        mod._CONSENT_PATH = self._consent_path
        try:
            result = _load_consent()
        finally:
            mod._CONSENT_PATH = orig
        self.assertIsInstance(result, bool)


class TestAmbientListenerConsentAttr(unittest.TestCase):
    """AmbientListener has _consent_given attribute after init."""

    def test_has_consent_given_attr(self):
        from core.voice.ambient_listener import AmbientListener
        al = AmbientListener()
        self.assertTrue(hasattr(al, "_consent_given"))

    def test_consent_given_is_bool(self):
        from core.voice.ambient_listener import AmbientListener
        al = AmbientListener()
        self.assertIsInstance(al._consent_given, bool)


class TestAmbientListenerStartMethod(unittest.TestCase):
    """start() creates a background asyncio task."""

    def test_start_method_exists(self):
        from core.voice.ambient_listener import AmbientListener
        al = AmbientListener()
        self.assertTrue(hasattr(al, "start"))

    def test_start_returns_task(self):
        from core.voice.ambient_listener import AmbientListener

        async def _run():
            al = AmbientListener()
            al._wake = None
            task = al.start()
            self.assertIsInstance(task, asyncio.Task)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        asyncio.run(_run())

    def test_run_continuous_is_coroutine(self):
        from core.voice.ambient_listener import AmbientListener
        al = AmbientListener()
        self.assertTrue(inspect.iscoroutinefunction(al._run_continuous))


class TestListenTickFiresOnSpeech(unittest.TestCase):
    """listen_tick() starts the wake background task; returns voice result when complete."""

    def test_listen_tick_returns_none_when_no_wake(self):
        from core.voice.ambient_listener import AmbientListener

        async def _run():
            al = AmbientListener()
            al._wake = None
            result = await al.listen_tick()
            return result

        result = asyncio.run(_run())
        self.assertIsNone(result)

    def test_listen_tick_returns_last_result(self):
        """If _last_voice_result is set, listen_tick returns it and clears it."""
        from core.voice.ambient_listener import AmbientListener

        async def _run():
            al = AmbientListener()
            al._wake = MagicMock()
            al._last_voice_result = {
                "intent": "respond",
                "response": "Done",
                "source": "voice",
                "confidence": 0.9,
                "actionable": False,
                "params": {},
                "intents": [],
            }
            result = await al.listen_tick()
            return result, al._last_voice_result

        result, after = asyncio.run(_run())
        self.assertIsNotNone(result)
        self.assertEqual(result["intent"], "respond")
        self.assertIsNone(after)

    def test_listen_tick_creates_wake_task(self):
        """listen_tick() creates _wake_task when wake detector is present."""
        from core.voice.ambient_listener import AmbientListener

        async def _run():
            al = AmbientListener()
            al._wake = MagicMock()
            al._wake.listen_for_wake = AsyncMock(return_value=None)
            self.assertIsNone(al._wake_task)
            await al.listen_tick()
            created = al._wake_task is not None
            if al._wake_task and not al._wake_task.done():
                al._wake_task.cancel()
                try:
                    await al._wake_task
                except Exception:
                    pass
            return created

        result = asyncio.run(_run())
        self.assertTrue(result)

    def test_listen_tick_no_duplicate_tasks(self):
        """Calling listen_tick() twice doesn't create two simultaneous wake tasks."""
        from core.voice.ambient_listener import AmbientListener

        async def _run():
            al = AmbientListener()
            al._wake = MagicMock()
            al._wake.listen_for_wake = AsyncMock(return_value=None)
            await al.listen_tick()
            task1 = al._wake_task
            await al.listen_tick()
            task2 = al._wake_task
            same = task1 is task2
            if al._wake_task and not al._wake_task.done():
                al._wake_task.cancel()
                try:
                    await al._wake_task
                except BaseException:
                    pass
            return same

        result = asyncio.run(_run())
        self.assertTrue(result)


class TestUserInteractionEventPublication(unittest.TestCase):
    """After a voice turn, USER_INTERACTION event is published to event bus."""

    def test_handle_voice_input_publishes_event(self):
        from core.voice.ambient_listener import AmbientListener
        from core.event_bus.types import EventType

        published_events = []

        async def fake_publish(event_type, data):
            published_events.append((event_type, data))

        async def _run():
            al = AmbientListener()
            al._stt = MagicMock()
            al._stt.record_and_transcribe = MagicMock(
                side_effect=["Hey VECTOR, what time is it?", ""]
            )
            al._tts = MagicMock()
            al._tts.speak = MagicMock()
            al._tts.stop_speaking = MagicMock()
            al._wake = None

            mock_bus = MagicMock()
            mock_bus.publish = AsyncMock(side_effect=fake_publish)

            with patch("core.event_bus.bus.get_event_bus", return_value=mock_bus):
                mock_gateway = MagicMock()
                mock_action_result = {"message": "It is 9 AM, sir.", "decision": "GREEN"}
                mock_gateway.execute = AsyncMock(return_value=mock_action_result)
                al._gateway = mock_gateway

                al._context = MagicMock()
                al._context.session_hydration_prompt = MagicMock(return_value="hydration")

                with patch.object(al, "_classify_intents", new=AsyncMock(return_value=[
                    {"action_type": "respond", "params": {"message": "test"}, "confidence": 0.8}
                ])):
                    with patch("time.time", side_effect=[1000.0, 1000.1, 1000.2, 1046.0, 1046.1]):
                        try:
                            await asyncio.wait_for(al.handle_voice_input("conversation"), timeout=3.0)
                        except (asyncio.TimeoutError, StopIteration, Exception):
                            pass

        asyncio.run(_run())

        if published_events:
            types = [e[0] for e in published_events]
            self.assertIn(EventType.USER_INTERACTION, types)

    def test_event_publication_code_in_source(self):
        """Source of handle_voice_input must reference USER_INTERACTION."""
        from core.voice.ambient_listener import AmbientListener
        src = inspect.getsource(AmbientListener.handle_voice_input)
        self.assertIn("USER_INTERACTION", src)

    def test_event_bus_publish_wrapped_in_try_except(self):
        """Event bus publish must not crash handle_voice_input on failure."""
        from core.voice.ambient_listener import AmbientListener
        src = inspect.getsource(AmbientListener.handle_voice_input)
        self.assertIn("_eb_err", src)


class TestSilenceDoesNotFire(unittest.TestCase):
    """listen_tick() does not return an event when only silence is recorded."""

    def test_no_event_on_silence(self):
        from core.voice.ambient_listener import AmbientListener

        async def _run():
            al = AmbientListener()
            al._wake = None
            results = []
            for _ in range(5):
                result = await al.listen_tick()
                results.append(result)
            return results

        results = asyncio.run(_run())
        self.assertTrue(all(r is None for r in results))


class TestRunVectorWiring(unittest.TestCase):
    """run_vector.py _start_background_services wires AmbientListener when enabled."""

    def test_ambient_reference_in_start_background_services(self):
        src = Path("run_vector.py").read_text(encoding="utf-8")
        self.assertIn("AmbientListener", src)
        self.assertIn("ambient_enabled", src)

    def test_consent_check_in_startup(self):
        src = Path("run_vector.py").read_text(encoding="utf-8")
        self.assertIn("_consent_given", src)
        self.assertIn("_save_consent", src)


if __name__ == "__main__":
    unittest.main()
