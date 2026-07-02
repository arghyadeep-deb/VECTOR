"""Regression tests for the LLM chat-vs-action intent gate (voice duplex).

Covers the 2026-07-02 fix: regex misses no longer force chat — an LLM gate
(vector-focus) classifies imperative utterances into governor task types.
Ollama is external, so mocking `chat` is allowed (testing.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.voice.realtime import classify_intent, classify_intent_llm


def test_regex_fast_path_still_wins():
    assert classify_intent("run the venture pipeline") == "venture_pipeline"
    assert classify_intent("scan reddit for problems") == "mine_social"


def test_no_verb_hint_skips_llm(monkeypatch):
    # No imperative verb → must return None WITHOUT calling the LLM.
    import core.inference.ollama_safe as ollama_safe

    def _boom(*a, **kw):
        raise AssertionError("LLM must not be called for pure chat")

    monkeypatch.setattr(ollama_safe, "chat", _boom)
    assert classify_intent_llm("good morning, how was your night") is None


def test_action_reply_parsed(monkeypatch):
    import core.inference.ollama_safe as ollama_safe
    monkeypatch.setattr(
        ollama_safe, "chat",
        lambda *a, **kw: "ACTION: generate interview prep report",
    )
    assert classify_intent_llm("generate the interview prep report") == \
        "generate interview prep report"


def test_chat_reply_returns_none(monkeypatch):
    import core.inference.ollama_safe as ollama_safe
    monkeypatch.setattr(ollama_safe, "chat", lambda *a, **kw: "CHAT")
    assert classify_intent_llm("check this out, my friend got a new car") is None


def test_llm_failure_degrades_to_chat(monkeypatch):
    import core.inference.ollama_safe as ollama_safe
    monkeypatch.setattr(ollama_safe, "chat", lambda *a, **kw: "")
    assert classify_intent_llm("run a full diagnostic on the system") is None


def test_oversized_task_type_rejected(monkeypatch):
    import core.inference.ollama_safe as ollama_safe
    monkeypatch.setattr(
        ollama_safe, "chat",
        lambda *a, **kw: "ACTION: " + "x" * 200,
    )
    assert classify_intent_llm("run something weird") is None


def test_config_gate_disables_llm(monkeypatch):
    from core.config import CONFIG
    monkeypatch.setitem(CONFIG["voice"], "llm_intent_fallback", False)
    import core.inference.ollama_safe as ollama_safe

    def _boom(*a, **kw):
        raise AssertionError("LLM must not be called when gate disabled")

    monkeypatch.setattr(ollama_safe, "chat", _boom)
    assert classify_intent_llm("run a full diagnostic") is None


if __name__ == "__main__":
    # real test, no mocks — requires Ollama with vector-focus
    ok = classify_intent("run the venture pipeline") == "venture_pipeline"
    print("✅ test_llm_intent_gate OK" if ok else "❌ FAILED")
