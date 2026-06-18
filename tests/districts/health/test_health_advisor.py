from __future__ import annotations

import pytest

from districts.health.health_advisor import HealthAdvisor


class TestRecommendationGeneration:
    def test_empty_metrics(self):
        advisor = HealthAdvisor()
        recs = advisor.generate_recommendations({}, {})
        assert isinstance(recs, list)
        assert len(recs) == 2

    def test_sleep_recommendations(self):
        advisor = HealthAdvisor()
        metrics = {"sleep_hours": 4.5}
        recs = advisor.generate_recommendations(metrics, {})
        types = [r["type"] for r in recs]
        assert "SLEEP_HYGIENE" in types

    def test_activity_recommendations(self):
        advisor = HealthAdvisor()
        metrics = {"steps": 2000}
        recs = advisor.generate_recommendations(metrics, {})
        types = [r["type"] for r in recs]
        assert "ACTIVITY_EXERCISE" in types

    def test_stress_recommendations(self):
        advisor = HealthAdvisor()
        metrics = {"hrv": 18.0, "stress_level": 0.8}
        recs = advisor.generate_recommendations(metrics, {})
        types = [r["type"] for r in recs]
        assert "STRESS_MANAGEMENT" in types

    def test_medical_attention_recommendations(self):
        advisor = HealthAdvisor()
        metrics = {"heart_rate": {"avg_value": 130}, "spo2": 90.0}
        recs = advisor.generate_recommendations(metrics, {})
        types = [r["type"] for r in recs]
        assert "MEDICAL_ATTENTION" in types

    def test_lifestyle_balance_compound(self):
        advisor = HealthAdvisor()
        metrics = {"sleep_hours": 5.0, "stress_level": 0.7, "steps": 3000}
        advisor._max_recs = 10
        recs = advisor.generate_recommendations(metrics, {})
        types = [r["type"] for r in recs]
        assert "LIFESTYLE_BALANCE" in types

    def test_routine_optimization(self):
        advisor = HealthAdvisor()
        trends = {"circadian": {"peak_hour": 14, "trough_hour": 3}}
        recs = advisor.generate_recommendations({}, trends)
        types = [r["type"] for r in recs]
        assert "ROUTINE_OPTIMIZATION" in types

    def test_priority_sorting(self):
        advisor = HealthAdvisor()
        metrics = {"sleep_hours": 4.0, "hrv": 15.0, "steps": 1000}
        recs = advisor.generate_recommendations(metrics, {})
        priorities = [r["priority"] for r in recs]
        assert priorities == sorted(priorities)

    def test_actionable_flag(self):
        advisor = HealthAdvisor()
        recs = advisor.generate_recommendations({"sleep_hours": 4.0}, {})
        for r in recs:
            assert "actionable" in r
