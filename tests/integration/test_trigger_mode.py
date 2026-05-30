"""Integration tests for TriggerMode / PresenceConfig (core/loop/presence.py)."""
import unittest


class TestPresenceConfig(unittest.TestCase):
    def setUp(self):
        # Reset module-level singleton
        import core.loop.presence as mod
        mod._presence_config = None

    def tearDown(self):
        import core.loop.presence as mod
        mod._presence_config = None

    def test_default_mode_is_proactive(self):
        from core.loop.presence import get_presence_config, TriggerMode
        cfg = get_presence_config()
        self.assertEqual(cfg.mode, TriggerMode.PROACTIVE)

    def test_singleton_cached(self):
        from core.loop.presence import get_presence_config
        a = get_presence_config()
        b = get_presence_config()
        self.assertIs(a, b)

    def test_reload_creates_fresh(self):
        from core.loop.presence import get_presence_config, reload_presence_config
        a = get_presence_config()
        b = reload_presence_config()
        self.assertIsNot(a, b)

    def test_dnd_crosses_midnight(self):
        from core.loop.presence import is_dnd_active, PresenceConfig, TriggerMode
        cfg = PresenceConfig(mode=TriggerMode.PROACTIVE, dnd_start_hour=23, dnd_end_hour=8)
        # Simulate hour 2 (between midnight and 8am)
        import unittest.mock
        with unittest.mock.patch("core.loop.presence.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = type("dt", (), {"hour": 2})()
            self.assertTrue(is_dnd_active(cfg))
        # Simulate hour 23
        with unittest.mock.patch("core.loop.presence.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = type("dt", (), {"hour": 23})()
            self.assertTrue(is_dnd_active(cfg))
        # Simulate hour 10 (during day — not DND)
        with unittest.mock.patch("core.loop.presence.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = type("dt", (), {"hour": 10})()
            self.assertFalse(is_dnd_active(cfg))


class TestAllowProactive(unittest.TestCase):
    def _cfg(self, mode, dnd_hour=10):
        from core.loop.presence import PresenceConfig, TriggerMode
        import unittest.mock
        return PresenceConfig(
            mode=TriggerMode(mode),
            dnd_start_hour=23,
            dnd_end_hour=8,
        )

    def test_reactive_blocks_all(self):
        from core.loop.presence import allow_proactive, PresenceConfig, TriggerMode
        cfg = PresenceConfig(mode=TriggerMode.REACTIVE)
        self.assertFalse(allow_proactive("nudge_engine", cfg=cfg))
        self.assertFalse(allow_proactive("daily_reviewer", cfg=cfg))

    def test_reactive_allows_emergency(self):
        from core.loop.presence import allow_proactive, PresenceConfig, TriggerMode
        cfg = PresenceConfig(mode=TriggerMode.REACTIVE)
        self.assertTrue(allow_proactive("threat_scout", is_emergency=True, cfg=cfg))

    def test_reactive_allows_security_district(self):
        from core.loop.presence import allow_proactive, PresenceConfig, TriggerMode
        cfg = PresenceConfig(mode=TriggerMode.REACTIVE)
        self.assertTrue(allow_proactive("any_agent", district="security", cfg=cfg))

    def test_proactive_suppressed_during_dnd(self):
        from core.loop.presence import allow_proactive, PresenceConfig, TriggerMode
        import unittest.mock
        cfg = PresenceConfig(mode=TriggerMode.PROACTIVE, dnd_start_hour=23, dnd_end_hour=8)
        with unittest.mock.patch("core.loop.presence.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = type("dt", (), {"hour": 2})()
            self.assertFalse(allow_proactive("nudge_engine", cfg=cfg))

    def test_proactive_allowed_outside_dnd(self):
        from core.loop.presence import allow_proactive, PresenceConfig, TriggerMode
        import unittest.mock
        cfg = PresenceConfig(mode=TriggerMode.PROACTIVE, dnd_start_hour=23, dnd_end_hour=8)
        with unittest.mock.patch("core.loop.presence.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = type("dt", (), {"hour": 14})()
            self.assertTrue(allow_proactive("nudge_engine", cfg=cfg))

    def test_hybrid_allows_listed_agents_outside_dnd(self):
        from core.loop.presence import allow_proactive, PresenceConfig, TriggerMode
        import unittest.mock
        cfg = PresenceConfig(
            mode=TriggerMode.HYBRID,
            dnd_start_hour=23,
            dnd_end_hour=8,
            allowed_proactive_agents=["nudge_engine"],
        )
        with unittest.mock.patch("core.loop.presence.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = type("dt", (), {"hour": 14})()
            self.assertTrue(allow_proactive("nudge_engine", cfg=cfg))
            self.assertFalse(allow_proactive("unlisted_agent", cfg=cfg))

    def test_hybrid_blocks_listed_agents_during_dnd(self):
        from core.loop.presence import allow_proactive, PresenceConfig, TriggerMode
        import unittest.mock
        cfg = PresenceConfig(
            mode=TriggerMode.HYBRID,
            dnd_start_hour=23,
            dnd_end_hour=8,
            allowed_proactive_agents=["nudge_engine"],
        )
        with unittest.mock.patch("core.loop.presence.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = type("dt", (), {"hour": 1})()
            self.assertFalse(allow_proactive("nudge_engine", cfg=cfg))

    def test_is_reactive_only(self):
        from core.loop.presence import is_reactive_only, PresenceConfig, TriggerMode
        self.assertTrue(is_reactive_only(PresenceConfig(mode=TriggerMode.REACTIVE)))
        self.assertFalse(is_reactive_only(PresenceConfig(mode=TriggerMode.PROACTIVE)))
        self.assertFalse(is_reactive_only(PresenceConfig(mode=TriggerMode.HYBRID)))


class TestConfigIntegration(unittest.TestCase):
    """Test that presence config reads from CONFIG correctly."""

    def test_from_config_loads_without_error(self):
        from core.loop.presence import PresenceConfig
        cfg = PresenceConfig.from_config()
        self.assertIsNotNone(cfg.mode)
        self.assertIsInstance(cfg.dnd_start_hour, int)
        self.assertIsInstance(cfg.dnd_end_hour, int)

    def test_env_override(self):
        import os
        import core.loop.presence as mod
        os.environ["VECTOR_PRESENCE_MODE"] = "reactive"
        mod._presence_config = None
        try:
            from core.loop.presence import get_presence_config, TriggerMode
            cfg = get_presence_config()
            self.assertEqual(cfg.mode, TriggerMode.REACTIVE)
        finally:
            del os.environ["VECTOR_PRESENCE_MODE"]
            mod._presence_config = None


if __name__ == "__main__":
    unittest.main()
