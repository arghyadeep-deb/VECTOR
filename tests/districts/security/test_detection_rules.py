import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import tempfile

import pytest
import yaml

from districts.security.detection_rules import DetectionRules, DetectionRule, RuleMatch


SAMPLE_RULES_YAML = """
rules:
  - id: "test_threshold"
    name: "Test Threshold Rule"
    description: "CPU > 95"
    source: "system_monitor"
    condition:
      type: "threshold"
      field: "cpu_percent"
      operator: ">"
      value: 95.0
    severity: 6
    response: ["alert"]

  - id: "test_pattern"
    name: "Test Pattern Rule"
    description: "Match error pattern"
    source: "log_aggregator"
    condition:
      type: "pattern"
      field: "message"
      pattern: "ERROR|FAILED"
    severity: 7
    response: ["alert", "notify"]

  - id: "test_rate"
    name: "Test Rate Rule"
    description: "Rate > 5 in 60s"
    source: "network_monitor"
    condition:
      type: "rate"
      field: "message"
      pattern: "conn"
      threshold: 5
      window: 60
    severity: 7

  - id: "test_composite"
    name: "Test Composite Rule"
    description: "CPU > 80 AND memory > 80"
    source: "system_monitor"
    condition:
      type: "composite"
      logic: "AND"
      conditions:
        - type: "threshold"
          field: "cpu_percent"
          operator: ">"
          value: 80.0
        - type: "threshold"
          field: "memory_percent"
          operator: ">"
          value: 80.0
    severity: 8

  - id: "disabled_rule"
    name: "Disabled Rule"
    enabled: false
    condition:
      type: "threshold"
      field: "cpu_percent"
      operator: ">"
      value: 0.0
    severity: 1
"""


@pytest.fixture
def rules_dir(tmp_path):
    f = tmp_path / "test_rules.yaml"
    f.write_text(SAMPLE_RULES_YAML, encoding="utf-8")
    return tmp_path


@pytest.fixture
def detector(rules_dir):
    return DetectionRules(rules_dir=str(rules_dir))


class TestLoadRules:
    def test_loads_rules(self, detector):
        assert len(detector._rules) >= 4

    def test_skips_disabled_rules(self, detector):
        ids = [r.id for r in detector._rules]
        assert "disabled_rule" not in ids

    def test_rule_attributes(self, detector):
        rule = next(r for r in detector._rules if r.id == "test_threshold")
        assert rule.name == "Test Threshold Rule"
        assert rule.severity == 6
        assert rule.condition_type == "threshold"


class TestThreshold:
    def test_threshold_exceeded(self, detector):
        event = {"cpu_percent": 96.0}
        matches = detector.evaluate(event)
        names = [m.rule_name for m in matches]
        assert "Test Threshold Rule" in names

    def test_threshold_not_exceeded(self, detector):
        event = {"cpu_percent": 50.0}
        matches = detector.evaluate(event)
        names = [m.rule_name for m in matches]
        assert "Test Threshold Rule" not in names

    def test_threshold_missing_field(self, detector):
        event = {"other": 100}
        matches = detector.evaluate(event)
        names = [m.rule_name for m in matches]
        assert "Test Threshold Rule" not in names


class TestPattern:
    def test_pattern_matches(self, detector):
        event = {"message": "ERROR: connection refused"}
        matches = detector.evaluate(event)
        names = [m.rule_name for m in matches]
        assert "Test Pattern Rule" in names

    def test_pattern_no_match(self, detector):
        event = {"message": "everything is fine"}
        matches = detector.evaluate(event)
        names = [m.rule_name for m in matches]
        assert "Test Pattern Rule" not in names

    def test_pattern_empty_field(self, detector):
        event = {"message": ""}
        matches = detector.evaluate(event)
        names = [m.rule_name for m in matches]
        assert "Test Pattern Rule" not in names


class TestRate:
    def test_rate_triggers_after_threshold(self, detector):
        for _ in range(6):
            matches = detector.evaluate({"message": "conn_established"})
        names = [m.rule_name for m in matches]
        assert "Test Rate Rule" in names

    def test_rate_below_threshold(self, detector):
        matches = detector.evaluate({"message": "conn_established"})
        names = [m.rule_name for m in matches]
        assert "Test Rate Rule" not in names


class TestComposite:
    def test_composite_and_both_true(self, detector):
        event = {"cpu_percent": 90.0, "memory_percent": 85.0}
        matches = detector.evaluate(event)
        names = [m.rule_name for m in matches]
        assert "Test Composite Rule" in names

    def test_composite_and_one_false(self, detector):
        event = {"cpu_percent": 90.0, "memory_percent": 50.0}
        matches = detector.evaluate(event)
        names = [m.rule_name for m in matches]
        assert "Test Composite Rule" not in names


class TestHotReload:
    def test_hot_reload_adds_rules(self, detector, rules_dir):
        before = len(detector._rules)
        extra = rules_dir / "extra.yaml"
        extra.write_text("rules:\n  - id: extra\n    name: Extra\n    condition:\n      type: threshold\n      field: x\n      operator: '>'\n      value: 0\n    severity: 1\n", encoding="utf-8")
        count = detector.hot_reload()
        assert count > before

    def test_hot_reload_empty_dir(self, tmp_path):
        dr = DetectionRules(rules_dir=str(tmp_path))
        assert dr.hot_reload() == 0


class TestRuleMatch:
    def test_rule_match_has_required_fields(self):
        m = RuleMatch(rule_name="test", severity=5)
        assert m.rule_name == "test"
        assert m.severity == 5
        assert m.triggered_at != ""
