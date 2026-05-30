
import datetime
import json

import pytest

from districts.security.log_aggregator import LogAggregator, LogEvent


@pytest.fixture
def aggregator(tmp_path):
    db = tmp_path / "test_logs.db"
    return LogAggregator(db_path=str(db))


class TestLogEvent:
    def test_create_log_event(self):
        event = LogEvent(service="test", level="INFO", message="hello")
        assert event.service == "test"
        assert event.level == "INFO"
        assert event.correlation_id is None

    def test_to_row(self):
        event = LogEvent(service="test", level="WARNING", message="warn", module="mod")
        row = event.to_row()
        assert row["service"] == "test"
        assert row["level"] == "WARNING"
        assert isinstance(row["extra"], str)
        assert json.loads(row["extra"]) == {}


class TestStorage:
    def test_ingest_and_query(self, aggregator):
        event = LogEvent(service="auth", level="ERROR", message="login failed")
        aggregator.ingest(event)
        aggregator._store_event(event)
        results = aggregator.query(level="ERROR")
        assert len(results) >= 1
        assert results[0]["message"] == "login failed"

    def test_query_by_service(self, aggregator):
        e1 = LogEvent(service="svc_a", message="a")
        e2 = LogEvent(service="svc_b", message="b")
        aggregator._store_event(e1)
        aggregator._store_event(e2)
        results = aggregator.query(service="svc_a")
        assert len(results) >= 1
        assert results[0]["service"] == "svc_a"

    def test_query_empty(self, aggregator):
        assert aggregator.query() == []


class TestStats:
    def test_get_stats_empty(self, aggregator):
        stats = aggregator.get_stats()
        assert stats["total"] == 0

    def test_get_stats_with_data(self, aggregator):
        aggregator._store_event(LogEvent(service="s1", level="INFO", message="m1"))
        aggregator._store_event(LogEvent(service="s2", level="ERROR", message="m2"))
        stats = aggregator.get_stats()
        assert stats["total"] == 2
        assert stats["by_level"].get("INFO", 0) == 1
        assert stats["by_level"].get("ERROR", 0) == 1


class TestRetention:
    def test_prune_old_entries(self, aggregator):
        old_event = LogEvent(
            service="test", level="INFO", message="old",
            timestamp=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=60),
        )
        aggregator._store_event(old_event)
        aggregator._store_event(LogEvent(service="test", level="INFO", message="new"))
        pruned = aggregator.prune_retention(days=30)
        assert pruned >= 1
        remaining = aggregator.get_stats()
        assert remaining["total"] == 1


class TestSink:
    def test_make_sink(self, aggregator):
        sink = aggregator.make_sink()
        assert callable(sink)
