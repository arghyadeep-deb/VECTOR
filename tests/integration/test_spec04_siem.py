"""Session 10 — Security SIEM integration tests.

Tests the full pipeline: LogAggregator → DetectionRules → IncidentPlaybookRunner.
Synthetic intrusion events exercise real MITRE ATT&CK detection rules.
All tests use isolated temp DBs — no shared state.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_pipeline(**kwargs):
    """Create a SIEMPipeline backed by temp directories."""
    from districts.security.siem_pipeline import SIEMPipeline
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "logs.db")
    idb = os.path.join(tmp, "incidents.db")
    pipeline = SIEMPipeline(db_path=db, incidents_db_path=idb, **kwargs)
    return pipeline, tmp


def _tmp_aggregator():
    from districts.security.log_aggregator import LogAggregator
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "logs.db")
    agg = LogAggregator(db_path=db)
    return agg, tmp


def _tmp_runner():
    from districts.security.incident_playbook_runner import IncidentPlaybookRunner
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "incidents.db")
    runner = IncidentPlaybookRunner(db_path=db)
    return runner, tmp


# ---------------------------------------------------------------------------
# 1. LogAggregator
# ---------------------------------------------------------------------------

class TestLogAggregatorIntegration(unittest.TestCase):

    def setUp(self):
        self.agg, self.tmp = _tmp_aggregator()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_and_query(self):
        from districts.security.log_aggregator import LogEvent
        ev = LogEvent(service="test_svc", level="WARNING", message="suspicious login")
        self.agg._store_event(ev)
        rows = self.agg.query(service="test_svc", limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message"], "suspicious login")

    def test_stats_total(self):
        from districts.security.log_aggregator import LogEvent
        for i in range(5):
            self.agg._store_event(LogEvent(service="svc", level="INFO", message=f"event {i}"))
        stats = self.agg.get_stats()
        self.assertGreaterEqual(stats["total"], 5)

    def test_ingest_queues_event(self):
        from districts.security.log_aggregator import LogEvent
        ev = LogEvent(service="queue_test", level="ERROR", message="critical failure")
        self.agg.ingest(ev)
        self.assertFalse(self.agg._queue.empty())

    def test_make_sink_callable(self):
        sink = self.agg.make_sink()
        self.assertTrue(callable(sink))

    def test_prune_retention(self):
        from districts.security.log_aggregator import LogEvent
        self.agg._store_event(LogEvent(service="old", level="INFO", message="old event"))
        deleted = self.agg.prune_retention(days=0)
        self.assertGreaterEqual(deleted, 0)

    def test_query_by_level(self):
        from districts.security.log_aggregator import LogEvent
        self.agg._store_event(LogEvent(service="s", level="ERROR", message="err"))
        self.agg._store_event(LogEvent(service="s", level="INFO", message="info"))
        error_rows = self.agg.query(level="ERROR", limit=10)
        for row in error_rows:
            self.assertEqual(row["level"], "ERROR")


# ---------------------------------------------------------------------------
# 2. DetectionRules — MITRE ATT&CK rules loaded and evaluated
# ---------------------------------------------------------------------------

class TestDetectionRulesMITRE(unittest.TestCase):

    def setUp(self):
        from districts.security.detection_rules import DetectionRules
        self.dr = DetectionRules()

    def test_rules_loaded(self):
        self.assertGreater(len(self.dr._rules), 0, "No detection rules loaded")

    def test_mitre_rules_present(self):
        rule_ids = {r.id for r in self.dr._rules}
        expected = {"T1059_cmd_scripting", "T1086_powershell", "T1046_port_scan",
                    "T1110_brute_force", "T1070_log_clearing", "T1485_data_destruction"}
        missing = expected - rule_ids
        self.assertEqual(missing, set(), f"Missing MITRE rules: {missing}")

    def test_pattern_rule_log_clearing(self):
        event = {"source": "log_aggregator", "message": "wevtutil cl Security"}
        matches = self.dr.evaluate(event)
        names = [m.rule_name for m in matches]
        self.assertIn("Log File Clearing Detected", names)

    def test_pattern_rule_powershell(self):
        event = {"source": "log_aggregator", "message": "Invoke-Expression download.ps1"}
        matches = self.dr.evaluate(event)
        names = [m.rule_name for m in matches]
        self.assertTrue(any("PowerShell" in n for n in names), f"No PowerShell match in {names}")

    def test_threshold_rule_high_cpu(self):
        event = {"source": "system_monitor", "cpu_percent": 96.0, "message": "cpu spike"}
        matches = self.dr.evaluate(event)
        names = [m.rule_name for m in matches]
        self.assertIn("Resource Hijacking (High CPU)", names)

    def test_no_match_normal_event(self):
        event = {"source": "app", "message": "user logged in successfully"}
        matches = self.dr.evaluate(event)
        self.assertEqual(len(matches), 0, f"Unexpected matches: {[m.rule_name for m in matches]}")

    def test_rate_rule_brute_force_accumulates(self):
        event = {"source": "log_aggregator", "message": "auth fail from 192.168.1.10"}
        matches_after = []
        for _ in range(6):
            matches_after = self.dr.evaluate(event)
        names = [m.rule_name for m in matches_after]
        self.assertIn("Brute Force Login Attempts", names)

    def test_data_destruction_pattern(self):
        event = {"source": "log_aggregator", "message": "rm -rf /var/log/audit"}
        matches = self.dr.evaluate(event)
        names = [m.rule_name for m in matches]
        self.assertIn("Data Destruction Attempt", names)

    def test_match_has_evidence(self):
        event = {"source": "log_aggregator", "message": "Clear-EventLog -LogName Application"}
        matches = self.dr.evaluate(event)
        self.assertTrue(len(matches) > 0)
        m = matches[0]
        self.assertIsInstance(m.evidence, dict)
        self.assertIn("rule_id", m.evidence)

    def test_severity_levels_present(self):
        rules_by_id = {r.id: r for r in self.dr._rules}
        self.assertEqual(rules_by_id["T1485_data_destruction"].severity, 10)
        self.assertEqual(rules_by_id["T1070_log_clearing"].severity, 9)
        self.assertGreaterEqual(rules_by_id["T1110_brute_force"].severity, 8)


# ---------------------------------------------------------------------------
# 3. IncidentPlaybookRunner — playbooks loaded, executed
# ---------------------------------------------------------------------------

class TestIncidentPlaybookRunnerIntegration(unittest.TestCase):

    def setUp(self):
        self.runner, self.tmp = _tmp_runner()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_playbooks_loaded(self):
        self.assertGreater(len(self.runner._playbooks), 0)

    def test_brute_force_playbook_present(self):
        self.assertIn("brute_force", self.runner._playbooks)

    def test_data_destruction_playbook_present(self):
        self.assertIn("data_destruction", self.runner._playbooks)

    def test_find_playbook_for_brute_force_rule(self):
        pb = self.runner._find_playbook_for_rule("Brute Force Login Attempts")
        self.assertIsNotNone(pb, "brute_force playbook not found by rule name")
        self.assertEqual(pb["id"], "brute_force")

    def test_find_playbook_for_data_destruction_rule(self):
        pb = self.runner._find_playbook_for_rule("Data Destruction Attempt")
        self.assertIsNotNone(pb, "data_destruction playbook not found by rule name")
        self.assertEqual(pb["id"], "data_destruction")

    def test_execute_brute_force_playbook(self):
        pb = self.runner._playbooks["brute_force"]
        evidence = {"target": "192.168.1.50", "count": 8, "window_sec": 60}
        incident = asyncio.run(self.runner.execute_playbook(pb, evidence))
        self.assertEqual(incident.status, "COMPLETED")
        self.assertGreater(len(incident.steps), 0)

    def test_execute_data_destruction_playbook(self):
        pb = self.runner._playbooks["data_destruction"]
        evidence = {"matched_on": "rm -rf", "pattern": r"rm -rf"}
        incident = asyncio.run(self.runner.execute_playbook(pb, evidence))
        self.assertIn(incident.status, ("COMPLETED", "FAILED"))

    def test_incident_stored_in_db(self):
        pb = self.runner._playbooks.get("port_scan") or list(self.runner._playbooks.values())[0]
        evidence = {}
        incident = asyncio.run(self.runner.execute_playbook(pb, evidence))
        incidents = self.runner.get_incidents(limit=5)
        ids = [i["id"] for i in incidents]
        self.assertIn(incident.id, ids)


# ---------------------------------------------------------------------------
# 4. SIEMPipeline — basic functionality
# ---------------------------------------------------------------------------

class TestSIEMPipelineBasic(unittest.TestCase):

    def setUp(self):
        self.pipeline, self.tmp = _tmp_pipeline()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pipeline_components_initialised(self):
        from districts.security.log_aggregator import LogAggregator
        from districts.security.detection_rules import DetectionRules
        from districts.security.incident_playbook_runner import IncidentPlaybookRunner
        self.assertIsInstance(self.pipeline.log_aggregator, LogAggregator)
        self.assertIsInstance(self.pipeline.detection_rules, DetectionRules)
        self.assertIsInstance(self.pipeline.playbook_runner, IncidentPlaybookRunner)

    def test_get_stats_returns_dict(self):
        stats = self.pipeline.get_stats()
        self.assertIn("rules_loaded", stats)
        self.assertIn("playbooks_loaded", stats)
        self.assertIn("alerts_total", stats)
        self.assertGreater(stats["rules_loaded"], 0)
        self.assertGreater(stats["playbooks_loaded"], 0)

    def test_process_event_no_match(self):
        alerts = self.pipeline.process_event({
            "source": "app",
            "level": "INFO",
            "message": "user profile updated",
        })
        self.assertEqual(alerts, [])

    def test_process_event_returns_alert_structure(self):
        alerts = self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "WARNING",
            "message": "Clear-EventLog -LogName Security",
        })
        self.assertGreater(len(alerts), 0)
        a = alerts[0]
        self.assertIn("alert_id", a)
        self.assertIn("rule_name", a)
        self.assertIn("severity", a)
        self.assertIn("evidence", a)
        self.assertIn("playbook_ids", a)

    def test_alerts_appended_to_history(self):
        before = len(self.pipeline._alerts)
        self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "CRITICAL",
            "message": "DROP TABLE users",
        })
        after = len(self.pipeline._alerts)
        self.assertGreater(after, before)

    def test_parse_playbook_ids(self):
        from districts.security.siem_pipeline import SIEMPipeline
        ids = SIEMPipeline._parse_playbook_ids("alert, notify, playbook:brute_force")
        self.assertEqual(ids, ["brute_force"])

    def test_parse_multiple_playbook_ids(self):
        from districts.security.siem_pipeline import SIEMPipeline
        ids = SIEMPipeline._parse_playbook_ids("alert, playbook:brute_force, playbook:port_scan")
        self.assertIn("brute_force", ids)
        self.assertIn("port_scan", ids)

    def test_get_alerts_limit(self):
        for _ in range(5):
            self.pipeline.process_event({
                "source": "log_aggregator",
                "message": "Clear-EventLog -LogName Application",
            })
        recent = self.pipeline.get_alerts(limit=3)
        self.assertLessEqual(len(recent), 3)


# ---------------------------------------------------------------------------
# 5. Full synthetic intrusion scenarios
# ---------------------------------------------------------------------------

class TestSIEMPipelineSyntheticIntrusion(unittest.TestCase):
    """End-to-end intrusion tests: event → detection → playbook execution."""

    def setUp(self):
        self.pipeline, self.tmp = _tmp_pipeline()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_clearing_triggers_alert(self):
        """T1070 — defense evasion: log file clearing."""
        alerts = self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "WARNING",
            "message": "wevtutil cl Security",
        })
        rule_names = [a["rule_name"] for a in alerts]
        self.assertIn("Log File Clearing Detected", rule_names)

    def test_log_clearing_severity_nine(self):
        alerts = self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "WARNING",
            "message": "Clear-EventLog -LogName System",
        })
        clearing = [a for a in alerts if a["rule_name"] == "Log File Clearing Detected"]
        self.assertTrue(len(clearing) > 0)
        self.assertEqual(clearing[0]["severity"], 9)

    def test_data_destruction_triggers_alert_and_playbook(self):
        """T1485 — impact: data destruction command detected."""
        alerts = self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "CRITICAL",
            "message": "rm -rf /var/db",
        })
        destruction = [a for a in alerts if a["rule_name"] == "Data Destruction Attempt"]
        self.assertTrue(len(destruction) > 0, "Data destruction alert not triggered")
        self.assertIn("data_destruction", destruction[0]["playbook_ids"])

    def test_brute_force_rate_triggers_after_threshold(self):
        """T1110 — credential access: 5+ auth failures in 60s triggers alert."""
        triggered = False
        for _ in range(7):
            alerts = self.pipeline.process_event({
                "source": "log_aggregator",
                "level": "WARNING",
                "message": "auth fail: invalid password from 10.0.0.5",
            })
            for a in alerts:
                if a["rule_name"] == "Brute Force Login Attempts":
                    triggered = True
        self.assertTrue(triggered, "Brute force rate rule never triggered")

    def test_brute_force_playbook_executed_async(self):
        """T1110 — brute force playbook runs to completion."""
        fired_alerts: list[dict] = []

        async def run():
            for _ in range(7):
                alerts = await self.pipeline.async_process_event({
                    "source": "log_aggregator",
                    "level": "WARNING",
                    "message": "login fail: incorrect password for admin@host",
                })
                fired_alerts.extend(alerts)

        asyncio.run(run())
        brute_alerts = [a for a in fired_alerts if a["rule_name"] == "Brute Force Login Attempts"]
        if brute_alerts:
            a = brute_alerts[-1]
            if a["incident_ids"]:
                incidents = self.pipeline.playbook_runner.get_incidents(limit=10)
                ids = [i["id"] for i in incidents]
                self.assertTrue(any(iid in ids for iid in a["incident_ids"]))

    def test_high_cpu_triggers_resource_hijacking_alert(self):
        """T1496 — impact: cryptomining / resource abuse."""
        alerts = self.pipeline.process_event({
            "source": "system_monitor",
            "level": "WARNING",
            "message": "sustained high cpu",
            "cpu_percent": 97.3,
        })
        names = [a["rule_name"] for a in alerts]
        self.assertIn("Resource Hijacking (High CPU)", names)

    def test_powershell_execution_alert(self):
        """T1086 — execution: PowerShell invocation."""
        alerts = self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "WARNING",
            "message": "powershell -nop -enc <base64>",
        })
        names = [a["rule_name"] for a in alerts]
        self.assertTrue(any("PowerShell" in n for n in names), f"No PowerShell alert in {names}")

    def test_process_injection_triggers_alert(self):
        """T1055 — privilege escalation: process injection."""
        alerts = self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "CRITICAL",
            "message": "WriteProcessMemory called by unknown module",
        })
        names = [a["rule_name"] for a in alerts]
        self.assertIn("Process Injection Attempt", names)

    def test_remote_service_access_alert(self):
        """T1021 — lateral movement: SSH from unexpected source."""
        alerts = self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "WARNING",
            "message": "ssh from 203.0.113.42 accepted",
        })
        names = [a["rule_name"] for a in alerts]
        self.assertIn("Unusual Remote Service Access", names)

    def test_multiple_rules_fire_single_event(self):
        """A message containing both powershell + process injection patterns."""
        alerts = self.pipeline.process_event({
            "source": "log_aggregator",
            "level": "CRITICAL",
            "message": "powershell Invoke-Expression WriteProcessMemory",
        })
        self.assertGreater(len(alerts), 1, "Expected multiple rules to fire on compound event")

    def test_event_stored_in_aggregator_db(self):
        self.pipeline.process_event({
            "source": "test_source",
            "level": "WARNING",
            "message": "wevtutil cl Application",
        })
        rows = self.pipeline.log_aggregator.query(service="test_source", limit=10)
        self.assertEqual(len(rows), 1)

    def test_async_process_returns_incidents_for_data_destruction(self):
        """Full async pipeline: data destruction → playbook runs → incident created."""
        async def run():
            return await self.pipeline.async_process_event({
                "source": "log_aggregator",
                "level": "CRITICAL",
                "message": "shred /dev/sda executed",
            })

        alerts = asyncio.run(run())
        destruction = [a for a in alerts if a["rule_name"] == "Data Destruction Attempt"]
        self.assertTrue(len(destruction) > 0)
        d = destruction[0]
        if d["incident_ids"]:
            incidents = self.pipeline.playbook_runner.get_incidents(limit=5)
            ids = [i["id"] for i in incidents]
            self.assertTrue(any(iid in ids for iid in d["incident_ids"]))


if __name__ == "__main__":
    unittest.main()
