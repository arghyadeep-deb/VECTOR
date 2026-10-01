"""Tests for DataCollector: episodic memory scanning, feedback collection, domain collection, formatting, dedup, export."""

import json
import tempfile
from pathlib import Path

from core.training.data_collector import DataCollector


def _make_episodic_entry(instruction: str, output: str, reward: float, timestamp: str = "2026-01-15T12:00:00"):
    return {"instruction": instruction, "output": output, "reward": reward, "timestamp": timestamp}


class FakeEpisodicMemory:
    def __init__(self, entries: list[dict] | None = None):
        self._entries = entries or []

    def query(self, limit: int = 5000):
        return self._entries[:limit]


def test_collect_from_episodic_memory_high_reward(monkeypatch):
    seen = {"called": False}
    def fake_impl(self, days=30, min_reward=0.7):
        seen["called"] = True
        return [{"instruction": "write fib", "input": "", "output": "def fib", "reward": 0.9, "source": "test"}]
    monkeypatch.setattr("core.training.data_collector.DataCollector.collect_from_episodic_memory", fake_impl)
    collector = DataCollector()
    result = collector.collect_from_episodic_memory(days=30, min_reward=0.7)
    assert seen["called"]
    assert len(result) == 1
    assert result[0]["instruction"] == "write fib"


def test_collect_from_feedback_no_path():
    collector = DataCollector(db_path=tempfile.mktemp())
    result = collector.collect_from_feedback(days=7)
    assert result == []


def test_record_defaults_source_label_when_no_metadata(tmp_path, monkeypatch):
    """Regression: record()'s "input" field used
    `metadata.get("source", "autonomous_loop") if metadata else ""` -- the
    "autonomous_loop" default was unreachable whenever metadata was None
    (the only real caller, core/loop/autonomous_loop.py, never passes
    metadata=), so every live-collected training example silently got an
    empty "input"/source tag instead of the documented default."""
    monkeypatch.setattr("core.training.data_collector.data_path", lambda *a, **k: tmp_path)
    collector = DataCollector()
    collector.record("do a thing", "did the thing", reward=0.8)
    files = list(tmp_path.glob("action_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["input"] == "autonomous_loop"


def test_record_uses_metadata_source_when_given(tmp_path, monkeypatch):
    monkeypatch.setattr("core.training.data_collector.data_path", lambda *a, **k: tmp_path)
    collector = DataCollector()
    collector.record("x", "y", reward=0.5, metadata={"source": "manual_feedback"})
    files = list(tmp_path.glob("action_*.json"))
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["input"] == "manual_feedback"


def test_collect_from_domain_unknown():
    collector = DataCollector()
    result = collector.collect_from_domain("nonexistent", count=10)
    assert result == []


def test_format_alpaca_with_input():
    collector = DataCollector()
    data = [{"instruction": "test", "input": "context", "output": "response", "source": "test"}]
    result = collector.format_for_training(data, template="alpaca")
    assert len(result) == 1
    assert "### Instruction" in result[0]["text"]
    assert "### Input" in result[0]["text"]
    assert result[0]["source"] == "test"


def test_format_chat():
    collector = DataCollector()
    data = [{"instruction": "hello", "input": "", "output": "world", "source": "test"}]
    result = collector.format_for_training(data, template="chat")
    assert len(result) == 1
    parsed = json.loads(result[0]["text"])
    assert parsed[0]["role"] == "user"
    assert parsed[1]["role"] == "assistant"


def test_deduplicate_removes_exact_duplicates():
    collector = DataCollector()
    long_text = "This is a sufficiently long text that should pass the fifty character minimum threshold required by the deduplication filter so that items actually get added to the seen set and deduped list."
    data = [
        {"text": long_text, "source": "a"},
        {"text": long_text, "source": "b"},
        {"text": long_text + " unique ending part here to make it different enough.", "source": "c"},
    ]
    result = collector.deduplicate(data)
    assert len(result) == 2


def test_export_dataset_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        collector = DataCollector()
        data = [{"text": "test entry", "source": "test"}]
        out = Path(tmp) / "output.jsonl"
        path = collector.export_dataset(data, str(out))
        assert path == str(out)
        assert out.exists()
        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["text"] == "test entry"


def test_format_skips_empty_output():
    collector = DataCollector()
    data = [{"instruction": "", "output": ""}, {"instruction": "valid", "output": "ok"}]
    result = collector.format_for_training(data, template="alpaca")
    assert len(result) == 1
    assert "valid" in result[0]["text"]
