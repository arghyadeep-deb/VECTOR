import pytest
from unittest.mock import AsyncMock, MagicMock

from districts.home_assistant.voice_bridge import IntentMapper, VoiceCommand, ConfirmDialog, VoiceBridge, EntityResolver
from districts.home_assistant.entity_manager import HAEntity, EntityManager


class TestIntentMapper:
    def setup_method(self):
        self.mapper = IntentMapper()

    def test_turn_on(self):
        result = self.mapper.parse("turn on living room light")
        assert result is not None
        assert result.intent == "turn_on"
        assert "living room light" in result.entities

    def test_turn_off(self):
        result = self.mapper.parse("turn off kitchen light")
        assert result is not None
        assert result.intent == "turn_off"

    def test_set_value(self):
        result = self.mapper.parse("set dimmer to 50")
        assert result is not None
        assert result.intent == "set_value"
        assert result.params.get("value") == "50"

    def test_lock(self):
        result = self.mapper.parse("lock front door")
        assert result is not None
        assert result.intent == "lock"

    def test_nonsense(self):
        result = self.mapper.parse("what is the meaning of life")
        assert result is None


class TestConfirmDialog:
    def test_needs_confirmation_lock(self):
        cmd = VoiceCommand(raw_text="lock front door", intent="lock", entities=["front door"], domain="lock")
        assert ConfirmDialog.needs_confirmation(cmd) is True

    def test_no_confirmation_light(self):
        cmd = VoiceCommand(raw_text="turn on light", intent="turn_on", entities=["light"], domain="light")
        assert ConfirmDialog.needs_confirmation(cmd) is False

    def test_format_confirmation(self):
        cmd = VoiceCommand(raw_text="lock door", intent="lock", entities=["front door"])
        msg = ConfirmDialog.format_confirmation(cmd)
        assert "Are you sure" in msg


class TestVoiceBridge:
    @pytest.mark.asyncio
    async def test_process_no_intent(self):
        mgr = EntityManager()
        conn = AsyncMock()
        bridge = VoiceBridge(mgr, conn)
        result = await bridge.process("blah blah blah")
        assert "couldn't understand" in result.lower()

    @pytest.mark.asyncio
    async def test_process_high_risk_confirms(self):
        mgr = EntityManager()
        conn = AsyncMock()
        bridge = VoiceBridge(mgr, conn)
        result = await bridge.process("lock front door")
        assert "Are you sure" in result
