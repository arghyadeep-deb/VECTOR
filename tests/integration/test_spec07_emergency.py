"""Session 13 — Emergency Response integration tests.

Verifies:
- EmergencyDetector: rules loaded, signal detection, dedup, domain signals
- SeverityClassifier: LOW/MEDIUM/HIGH/CRITICAL scoring, compound detection, acknowledged modifier
- RunbookExecutor: execute() returns ActionResult list, per-runbook execution
- EscalationManager(test_mode=True): tiered steps, acknowledge stops escalation, pause/resume
- EmergencyResponseSystem: health check, event pipeline, emit_signal
"""
from __future__ import annotations

import asyncio
import time
import unittest
from dataclasses import dataclass


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. EmergencyDetector
# ---------------------------------------------------------------------------

class TestEmergencyDetector(unittest.TestCase):

    def setUp(self):
        from districts.emergency.detector import EmergencyDetector
        self.detector = EmergencyDetector()

    def test_default_rules_loaded(self):
        rules = self.detector.get_rules()
        self.assertGreaterEqual(len(rules), 18)

    def test_heart_rate_stopped_triggers(self):
        event = _run(self.detector.process_signal("health", "heart_rate_stopped", 0))
        self.assertIsNotNone(event)
        self.assertEqual(event.signal_name, "heart_rate_stopped")

    def test_heart_rate_normal_not_triggered(self):
        event = _run(self.detector.process_signal("health", "heart_rate_stopped", 72))
        self.assertIsNone(event)

    def test_heart_rate_critical_low_triggers(self):
        event = _run(self.detector.process_signal("health", "heart_rate_critical", 35))
        self.assertIsNotNone(event)

    def test_intrusion_detected_triggers(self):
        event = _run(self.detector.process_signal("security", "intrusion_detected", True))
        self.assertIsNotNone(event)
        self.assertEqual(event.domain, "security")

    def test_disk_full_triggers_at_96_percent(self):
        event = _run(self.detector.process_signal("system", "disk_full", 96))
        self.assertIsNotNone(event)

    def test_disk_full_not_triggered_below_threshold(self):
        event = _run(self.detector.process_signal("system", "disk_full", 94))
        self.assertIsNone(event)

    def test_battery_critical_triggers_below_10(self):
        event = _run(self.detector.process_signal("battery", "battery_critical", 5))
        self.assertIsNotNone(event)

    def test_high_cpu_triggers_above_90(self):
        event = _run(self.detector.process_signal("system", "high_cpu", 92))
        self.assertIsNotNone(event)

    def test_high_cpu_not_triggered_at_90_or_below(self):
        event = _run(self.detector.process_signal("system", "high_cpu", 90))
        self.assertIsNone(event)

    def test_dedup_returns_none_for_same_signal_within_window(self):
        src = "test_dedup_same"
        _run(self.detector.process_signal("security", "intrusion_detected", True, source=src))
        second = _run(self.detector.process_signal("security", "intrusion_detected", True, source=src))
        self.assertIsNone(second)

    def test_different_source_bypasses_dedup(self):
        _run(self.detector.process_signal("security", "intrusion_detected", True, source="src_A"))
        event = _run(self.detector.process_signal("security", "intrusion_detected", True, source="src_B"))
        self.assertIsNotNone(event)

    def test_event_has_required_fields(self):
        event = _run(self.detector.process_signal("disk", "disk_critical", 96, source="evt_fields_test"))
        self.assertIsNotNone(event)
        self.assertTrue(event.event_id)
        self.assertEqual(event.domain, "disk")
        self.assertEqual(event.signal_name, "disk_critical")
        self.assertGreater(event.detected_at, 0)

    def test_subscribe_signal_returns_queue(self):
        queue = self.detector.subscribe_signal("health")
        self.assertIsInstance(queue, asyncio.Queue)

    def test_internet_down_triggers(self):
        event = _run(self.detector.process_signal("network", "internet_down", True, source="inet_test"))
        self.assertIsNotNone(event)


# ---------------------------------------------------------------------------
# 2. SeverityClassifier
# ---------------------------------------------------------------------------

class TestSeverityClassifier(unittest.TestCase):

    def setUp(self):
        from districts.emergency.classifier import SeverityClassifier
        from districts.emergency.detector import EmergencyEvent
        self.classifier = SeverityClassifier()
        self.EmergencyEvent = EmergencyEvent

    def _make_event(self, domain="security", signal="intrusion_detected", eid=None):
        import uuid
        return self.EmergencyEvent(
            event_id=eid or str(uuid.uuid4())[:8],
            domain=domain,
            signal_name=signal,
            raw_value=True,
            raw_message=f"{domain} event",
            detected_at=time.time(),
            source="test",
        )

    def test_classify_returns_scored_emergency(self):
        from districts.emergency.classifier import ScoredEmergency
        event = self._make_event()
        scored = self.classifier.classify(event)
        self.assertIsInstance(scored, ScoredEmergency)

    def test_severity_score_in_range(self):
        event = self._make_event()
        scored = self.classifier.classify(event)
        self.assertGreaterEqual(scored.severity_score, 0.0)
        self.assertLessEqual(scored.severity_score, 1.0)

    def test_severity_is_valid_label(self):
        event = self._make_event()
        scored = self.classifier.classify(event)
        self.assertIn(scored.severity, ("CRITICAL", "HIGH", "MEDIUM", "LOW"))

    def test_security_scores_higher_than_battery(self):
        sec_event = self._make_event("security", "intrusion_detected", "sec-001")
        bat_event = self._make_event("battery", "battery_low", "bat-001")
        sec_cls = self.classifier.__class__()
        bat_cls = self.classifier.__class__()
        sec = sec_cls.classify(sec_event)
        bat = bat_cls.classify(bat_event)
        self.assertGreater(sec.severity_score, bat.severity_score)

    def test_compound_disk_full_after_high_ram_is_critical(self):
        from districts.emergency.classifier import SeverityClassifier
        cls = SeverityClassifier()
        ram_event = self.EmergencyEvent(
            event_id="ram-01", domain="system", signal_name="high_ram",
            raw_value=91, raw_message="RAM high", detected_at=time.time(), source="test",
        )
        cls.classify(ram_event)
        disk_event = self.EmergencyEvent(
            event_id="disk-01", domain="system", signal_name="disk_full",
            raw_value=96, raw_message="Disk full", detected_at=time.time(), source="test",
        )
        scored = cls.classify(disk_event)
        self.assertEqual(scored.severity, "CRITICAL")
        self.assertAlmostEqual(scored.severity_score, 1.0, places=5)

    def test_acknowledged_reduces_score(self):
        from districts.emergency.classifier import SeverityClassifier
        cls1 = SeverityClassifier()
        cls2 = SeverityClassifier()
        event1 = self._make_event("health", "heart_rate_high", "ack-01")
        event2 = self.EmergencyEvent(
            event_id="ack-01", domain="health", signal_name="heart_rate_high",
            raw_value=145, raw_message="HR high", detected_at=time.time(), source="test",
        )
        normal_score = cls1.classify(event1).severity_score
        cls2.mark_acknowledged("ack-01")
        ack_score = cls2.classify(event2).severity_score
        self.assertLess(ack_score, normal_score)

    def test_recommendation_for_critical_health(self):
        cls = self.classifier.__class__()
        event = self.EmergencyEvent(
            event_id="hr-crit", domain="health", signal_name="heart_rate_stopped",
            raw_value=0, raw_message="HR stopped", detected_at=time.time(), source="test",
        )
        # Inject prior HIGH health event to trigger compound → CRITICAL
        from districts.emergency.classifier import ScoredEmergency
        prior = ScoredEmergency(event=self.EmergencyEvent(
            event_id="prior-01", domain="health", signal_name="heart_rate_critical",
            raw_value=35, raw_message="HR low", detected_at=time.time(), source="test",
        ), severity="HIGH", severity_score=0.75, classified_at=time.time())
        cls._event_history.append(prior)
        scored = cls.classify(event)
        self.assertIsInstance(scored.recommendation, str)
        self.assertGreater(len(scored.recommendation), 0)

    def test_classified_at_is_recent(self):
        event = self._make_event("system", "high_cpu")
        t_before = time.time()
        scored = self.classifier.classify(event)
        t_after = time.time()
        self.assertGreaterEqual(scored.classified_at, t_before)
        self.assertLessEqual(scored.classified_at, t_after + 0.1)

    def test_confidence_in_range(self):
        event = self._make_event("network", "internet_down")
        scored = self.classifier.classify(event)
        self.assertGreaterEqual(scored.confidence, 0.0)
        self.assertLessEqual(scored.confidence, 1.0)

    def test_mark_acknowledged_stores_id(self):
        self.classifier.mark_acknowledged("evt-xyz")
        self.assertIn("evt-xyz", self.classifier._acknowledged_ids)

    def test_context_modifiers_is_list(self):
        event = self._make_event()
        scored = self.classifier.classify(event)
        self.assertIsInstance(scored.context_modifiers, list)

    def test_escalation_path_is_string(self):
        event = self._make_event()
        scored = self.classifier.classify(event)
        self.assertIsInstance(scored.escalation_path, str)


# ---------------------------------------------------------------------------
# 3. RunbookExecutor
# ---------------------------------------------------------------------------

class TestRunbookExecutor(unittest.TestCase):

    def setUp(self):
        from districts.emergency.runbook import RunbookExecutor
        from districts.emergency.classifier import ScoredEmergency
        from districts.emergency.detector import EmergencyEvent
        self.executor = RunbookExecutor()
        self.ScoredEmergency = ScoredEmergency
        self.EmergencyEvent = EmergencyEvent

    def _make_scored(self, signal_name="intrusion_detected", domain="security", severity="HIGH"):
        event = self.EmergencyEvent(
            event_id=f"rb-{signal_name[:6]}",
            domain=domain,
            signal_name=signal_name,
            raw_value=True,
            raw_message=f"Test {signal_name}",
            detected_at=time.time(),
            source="test",
        )
        return self.ScoredEmergency(
            event=event,
            severity=severity,
            severity_score=0.75,
            classified_at=time.time(),
        )

    def test_execute_returns_list(self):
        scored = self._make_scored()
        results = _run(self.executor.execute(scored))
        self.assertIsInstance(results, list)

    def test_intrusion_runbook_returns_result(self):
        scored = self._make_scored("intrusion_detected", "security")
        results = _run(self.executor.execute(scored))
        self.assertGreater(len(results), 0)

    def test_disk_full_runbook_has_actions(self):
        scored = self._make_scored("disk_full", "system")
        results = _run(self.executor.execute(scored))
        self.assertGreaterEqual(len(results), 1)

    def test_gpu_overheat_runbook_returns_three_results(self):
        scored = self._make_scored("gpu_temp_high", "system")
        results = _run(self.executor.execute(scored))
        self.assertEqual(len(results), 3)

    def test_health_critical_runbook_does_not_claim_notification_sent(self):
        # The runbook has no delivery channel; it must not report success for a
        # notification it never sent (delivery is the escalation pushover step).
        scored = self._make_scored("heart_rate_stopped", "health", "CRITICAL")
        results = _run(self.executor.execute(scored))
        self.assertFalse(results[0].success)

    def test_battery_critical_runbook_returns_one_result(self):
        scored = self._make_scored("battery_critical", "battery")
        results = _run(self.executor.execute(scored))
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)

    def test_unknown_signal_returns_no_runbook_result(self):
        scored = self._make_scored("unknown_signal_xyz", "system")
        results = _run(self.executor.execute(scored))
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertIn("no_runbook", results[0].output)

    def test_action_result_has_duration_ms(self):
        scored = self._make_scored("heart_rate_stopped", "health", "CRITICAL")
        results = _run(self.executor.execute(scored))
        self.assertGreaterEqual(results[0].duration_ms, 0)

    def test_action_result_has_output_field(self):
        scored = self._make_scored("heart_rate_stopped", "health")
        results = _run(self.executor.execute(scored))
        self.assertIsInstance(results[0].output, str)


# ---------------------------------------------------------------------------
# 4. EscalationManager
# ---------------------------------------------------------------------------

class TestEscalationManager(unittest.TestCase):

    def setUp(self):
        from districts.emergency.escalation import EscalationManager
        from districts.emergency.classifier import ScoredEmergency
        from districts.emergency.detector import EmergencyEvent
        self.EscalationManager = EscalationManager
        self.ScoredEmergency = ScoredEmergency
        self.EmergencyEvent = EmergencyEvent

    def _make_scored(self, severity="LOW", signal="disk_full", domain="system", eid=None):
        import uuid
        event = self.EmergencyEvent(
            event_id=eid or str(uuid.uuid4())[:8],
            domain=domain,
            signal_name=signal,
            raw_value=True,
            raw_message=f"{severity} test",
            detected_at=time.time(),
            source="test",
        )
        return self.ScoredEmergency(
            event=event,
            severity=severity,
            severity_score={"CRITICAL": 0.95, "HIGH": 0.75, "MEDIUM": 0.50, "LOW": 0.20}[severity],
            classified_at=time.time(),
        )

    def test_low_severity_gets_log_only(self):
        em = self.EscalationManager(test_mode=True)
        scored = self._make_scored("LOW")
        results = _run(em.escalate(scored))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "log_only")
        self.assertEqual(results[0]["status"], "ok")

    def test_medium_severity_gets_one_pushover_step(self):
        em = self.EscalationManager(test_mode=True)
        scored = self._make_scored("MEDIUM")
        results = _run(em.escalate(scored))
        self.assertEqual(len(results), 1)
        self.assertIn("pushover", results[0]["action"])

    def test_high_severity_gets_two_steps(self):
        em = self.EscalationManager(test_mode=True)
        scored = self._make_scored("HIGH")
        results = _run(em.escalate(scored))
        self.assertEqual(len(results), 2)

    def test_critical_severity_gets_three_steps(self):
        em = self.EscalationManager(test_mode=True)
        scored = self._make_scored("CRITICAL")
        results = _run(em.escalate(scored))
        self.assertEqual(len(results), 3)

    def test_critical_first_step_is_runbook(self):
        em = self.EscalationManager(test_mode=True)
        scored = self._make_scored("CRITICAL")
        results = _run(em.escalate(scored))
        self.assertEqual(results[0]["action"], "runbook_executed")

    def test_acknowledge_before_escalation_skips_all(self):
        em = self.EscalationManager(test_mode=True)
        scored = self._make_scored("CRITICAL", eid="ack-skip-01")
        em.acknowledge("ack-skip-01")
        results = _run(em.escalate(scored))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "already_acknowledged")
        self.assertEqual(results[0]["status"], "skipped")

    def test_pause_skips_all_steps(self):
        em = self.EscalationManager(test_mode=True)
        em.pause()
        scored = self._make_scored("CRITICAL")
        results = _run(em.escalate(scored))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action"], "paused")

    def test_resume_after_pause_resumes_escalation(self):
        em = self.EscalationManager(test_mode=True)
        em.pause()
        em.resume()
        scored = self._make_scored("LOW")
        results = _run(em.escalate(scored))
        self.assertEqual(results[0]["action"], "log_only")

    def test_results_are_list_of_dicts(self):
        em = self.EscalationManager(test_mode=True)
        scored = self._make_scored("HIGH")
        results = _run(em.escalate(scored))
        for r in results:
            self.assertIsInstance(r, dict)
            self.assertIn("action", r)
            self.assertIn("status", r)

    def test_escalation_log_grows_after_escalate(self):
        em = self.EscalationManager(test_mode=True)
        initial = len(em.get_state().escalation_log)
        scored = self._make_scored("LOW")
        _run(em.escalate(scored))
        self.assertEqual(len(em.get_state().escalation_log), initial + 1)

    def test_each_result_has_tier_delay_sec(self):
        em = self.EscalationManager(test_mode=True)
        scored = self._make_scored("HIGH")
        results = _run(em.escalate(scored))
        for r in results:
            self.assertIn("tier_delay_sec", r)

    def test_acceleration_flag_on_second_same_domain_call(self):
        em = self.EscalationManager(test_mode=True)
        first = self._make_scored("LOW", domain="security")
        _run(em.escalate(first))
        em._last_domain_times["security"] = time.time()
        second = self._make_scored("LOW", domain="security")
        _run(em.escalate(second))
        log = em.get_state().escalation_log
        self.assertTrue(log[-1]["accelerated"])


# ---------------------------------------------------------------------------
# 5. EmergencyResponseSystem — end-to-end
# ---------------------------------------------------------------------------

class TestEmergencyResponseSystemE2E(unittest.TestCase):

    def setUp(self):
        from districts.emergency.main import EmergencyResponseSystem
        # test_mode keeps escalation off the live notification API / audio alarms.
        self.system = EmergencyResponseSystem(test_mode=True)

    def test_system_initializes_without_error(self):
        self.assertIsNotNone(self.system)

    def test_get_health_returns_dict(self):
        health = self.system.get_health()
        self.assertIsInstance(health, dict)
        self.assertIn("running", health)
        self.assertIn("detector_rules", health)
        self.assertGreaterEqual(health["detector_rules"], 18)

    def test_get_health_not_running_before_start(self):
        health = self.system.get_health()
        self.assertFalse(health["running"])

    def test_emit_signal_returns_event_for_known_signal(self):
        event = _run(self.system.emit_signal("security", "intrusion_detected", True, source="e2e-intrusion"))
        self.assertIsNotNone(event)
        self.assertEqual(event.signal_name, "intrusion_detected")

    def test_emit_signal_returns_none_for_non_triggering_value(self):
        event = _run(self.system.emit_signal("battery", "battery_critical", 50, source="e2e-bat-ok"))
        self.assertIsNone(event)

    def test_process_event_pipeline_returns_without_error(self):
        from districts.emergency.detector import EmergencyEvent
        from districts.emergency.classifier import ScoredEmergency
        event = EmergencyEvent(
            event_id="e2e-pipe-01",
            domain="health",
            signal_name="heart_rate_stopped",
            raw_value=0,
            raw_message="Heart rate stopped",
            detected_at=time.time(),
            source="test",
        )
        scored = self.system._classifier.classify(event)
        actions = _run(self.system._runbook.execute(scored))
        self.assertIsInstance(actions, list)
        escalation_results = _run(self.system._escalation.escalate(scored, actions))
        self.assertIsInstance(escalation_results, list)
        self.assertGreater(len(escalation_results), 0)

    def test_acknowledge_registers_in_escalation_manager(self):
        self.system.acknowledge("e2e-ack-001")
        self.assertIn("e2e-ack-001", self.system._escalation._acknowledged)

    def test_get_state_returns_dict(self):
        state = self.system.get_state()
        self.assertIsInstance(state, dict)
        self.assertIn("running", state)
        self.assertIn("log_summary", state)

    def test_log_summary_has_expected_keys(self):
        state = self.system.get_state()
        summary = state["log_summary"]
        self.assertIn("total_emergencies", summary)
        self.assertIn("by_severity", summary)
        self.assertIn("chain_integrity", summary)


if __name__ == "__main__":
    unittest.main()
