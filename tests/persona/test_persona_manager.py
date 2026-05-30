from __future__ import annotations


import pytest
from core.persona.schemas import PersonaIdentity, ToneContext, PersonaState
from core.persona.identity import PersonaIdentityLoader
from core.persona.voice_tone import ToneModulator
from core.persona.evolution import PersonaEvolution
from core.persona.consistency import ConsistencyEnforcer, InconsistencyReport
from core.persona.persona_manager import PersonaManager


class TestSchemas:
    def test_persona_identity_defaults(self):
        identity = PersonaIdentity()
        assert identity.name == "VECTOR"
        assert "precise" in identity.core_traits
        assert identity.communication_defaults["formality"] == 0.7

    def test_tone_context_defaults(self):
        ctx = ToneContext()
        assert ctx.time_of_day == "afternoon"
        assert ctx.urgency == "normal"

    def test_persona_state_defaults(self):
        state = PersonaState()
        assert state.identity.name == "VECTOR"
        assert state.evolution_level == 0.0


class TestIdentity:
    def test_load_returns_identity(self, tmp_path):
        loader = PersonaIdentityLoader(data_dir=tmp_path)
        identity = loader.load()
        assert identity.name == "VECTOR"
        assert identity.owner_title == "sir"

    def test_system_prompt_fragment(self, tmp_path):
        loader = PersonaIdentityLoader(data_dir=tmp_path)
        fragment = loader.get_system_prompt_fragment()
        assert "[IDENTITY" in fragment
        assert "VECTOR" in fragment
        assert "precise" in fragment

    def test_identity_yaml_created(self, tmp_path):
        loader = PersonaIdentityLoader(data_dir=tmp_path)
        loader.load()
        assert (tmp_path / "identity.yaml").exists()


class TestVoiceTone:
    def test_modulate_returns_text(self):
        mod = ToneModulator()
        ctx = ToneContext(urgency="normal")
        result = mod.modulate("Hello sir", ctx)
        assert result == "Hello sir"

    def test_critical_urgency_prefix(self):
        mod = ToneModulator()
        ctx = ToneContext(urgency="critical")
        result = mod.modulate("Server is down", ctx)
        assert result.startswith("[URGENT]")

    def test_tone_instructions_has_sections(self):
        mod = ToneModulator()
        ctx = ToneContext(time_of_day="night", urgency="critical")
        instructions = mod.get_tone_instructions(ctx)
        assert "[TONE DIRECTIVES]" in instructions
        assert "time_of_day" in instructions
        assert "urgency" in instructions

    def test_infer_time_of_day(self):
        assert ToneModulator.infer_time_of_day(8) == "morning"
        assert ToneModulator.infer_time_of_day(14) == "afternoon"
        assert ToneModulator.infer_time_of_day(19) == "evening"
        assert ToneModulator.infer_time_of_day(2) == "night"


class TestEvolution:
    def test_record_signal(self, tmp_path):
        evo = PersonaEvolution(db_path=tmp_path / "evo.db")
        evo.record_signal("owner_interaction")
        traits = evo.get_evolved_traits()
        assert "confidence" in traits
        evo.close()

    def test_evolution_level_zero(self, tmp_path):
        evo = PersonaEvolution(db_path=tmp_path / "evo.db")
        assert evo.get_evolution_level() == 0.0
        evo.close()

    def test_evolution_level_increases(self, tmp_path):
        evo = PersonaEvolution(db_path=tmp_path / "evo.db")
        for _ in range(10):
            evo.record_signal("owner_interaction")
        level = evo.get_evolution_level()
        assert level > 0.0
        evo.close()

    def test_persistence(self, tmp_path):
        db = tmp_path / "evo.db"
        evo1 = PersonaEvolution(db_path=db)
        evo1.record_signal("task_completed")
        evo1.close()
        evo2 = PersonaEvolution(db_path=db)
        traits = evo2.get_evolved_traits()
        assert "reliability" in traits
        evo2.close()

    def test_should_deepen(self, tmp_path):
        evo = PersonaEvolution(db_path=tmp_path / "evo.db")
        for _ in range(50):
            evo.record_signal("owner_interaction")
        assert evo.should_deepen() is True
        evo.close()


class TestConsistency:
    def test_check_output_passthrough(self):
        enforcer = ConsistencyEnforcer()
        result = enforcer.check_output("health", "All systems nominal, sir.")
        assert result == "All systems nominal, sir."

    def test_audit_catches_casual(self):
        enforcer = ConsistencyEnforcer()
        reports = enforcer.audit_recent_outputs([
            {"district": "comms", "text": "No prob dude, I got this lol"},
        ])
        assert len(reports) >= 1
        severities = {r.severity for r in reports}
        assert "low" in severities or "medium" in severities

    def test_audit_clean_output(self):
        enforcer = ConsistencyEnforcer()
        reports = enforcer.audit_recent_outputs([
            {"district": "health", "text": "All systems are operating within normal parameters, sir."},
        ])
        assert len(reports) == 0


class TestPersonaManager:
    def test_get_persona_state(self):
        pm = PersonaManager()
        state = pm.get_persona_state()
        assert state.identity.name == "VECTOR"

    def test_inject_persona_adds_identity(self):
        pm = PersonaManager()
        result = pm.inject_persona("You are a helpful assistant.")
        assert "[IDENTITY" in result
        assert "VECTOR" in result

    def test_inject_persona_with_tone(self):
        pm = PersonaManager()
        ctx = ToneContext(time_of_day="night", urgency="normal")
        result = pm.inject_persona("Help me.", context=ctx)
        assert "[TONE DIRECTIVES]" in result

    def test_health_check(self):
        pm = PersonaManager()
        hc = pm.health_check()
        assert hc["identity_loaded"] is True
        assert "evolution_level" in hc

    def test_record_interaction(self):
        pm = PersonaManager()
        pm.record_interaction("owner", "positive")
        assert pm.health_check()["evolved_traits"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=15"])
