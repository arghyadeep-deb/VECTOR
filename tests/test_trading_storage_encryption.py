"""OD-20 regression coverage for all sensitive trading-storage artifacts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.graph import END, StateGraph

from core.trading.agents.utils.memory import TradingMemoryLog
from core.trading.graph.checkpointer import get_checkpointer, thread_id
from core.trading.graph.trading_graph import VectorTradingGraph
from core.trading.storage_crypto import read_encrypted_text


class _State(TypedDict):
    strategy: str


def _build_graph():
    builder = StateGraph(_State)
    builder.add_node("plan", lambda state: {"strategy": state["strategy"] + " / sized at 5%"})
    builder.set_entry_point("plan")
    builder.add_edge("plan", END)
    return builder


def _final_state(marker: str) -> dict:
    debate = {
        "bull_history": marker,
        "bear_history": "bear",
        "history": "debate",
        "current_response": "response",
        "judge_decision": "judge",
    }
    risk = {
        "aggressive_history": "aggressive",
        "conservative_history": "conservative",
        "neutral_history": "neutral",
        "history": "risk debate",
        "judge_decision": "risk judge",
    }
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2026-10-08",
        "market_report": marker,
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "investment_debate_state": debate,
        "trader_investment_plan": "buy with 5% position sizing",
        "risk_debate_state": risk,
        "investment_plan": "enter at 100",
        "final_trade_decision": "BUY",
    }


def test_checkpoint_roundtrip_is_sqlcipher_encrypted(tmp_path: Path) -> None:
    marker = "PRIVATE-CHECKPOINT-STRATEGY"
    config = {"configurable": {"thread_id": thread_id("AAPL", "2026-10-08")}}
    with get_checkpointer(tmp_path, "AAPL") as saver:
        graph = _build_graph().compile(checkpointer=saver)
        assert graph.invoke({"strategy": marker}, config=config)["strategy"].endswith("5%")
    with get_checkpointer(tmp_path, "AAPL") as saver:
        saved = saver.get_tuple(config)
        assert saved is not None
        assert marker in repr(saved.checkpoint)

    raw = (tmp_path / "checkpoints" / "AAPL.db").read_bytes()
    assert not raw.startswith(b"SQLite format 3\x00")
    assert marker.encode() not in raw
    assert b"checkpoints" not in raw


def test_checkpoint_plaintext_migration_keeps_backup(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints" / "MSFT.db"
    db.parent.mkdir(parents=True)
    plain = sqlite3.connect(db, check_same_thread=False)
    config = {"configurable": {"thread_id": thread_id("MSFT", "2026-10-08")}}
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        saver = SqliteSaver(plain)
        saver.setup()
        graph = _build_graph().compile(checkpointer=saver)
        graph.invoke({"strategy": "MIGRATED-STRATEGY"}, config=config)
    finally:
        plain.close()

    with get_checkpointer(tmp_path, "MSFT") as saver:
        saved = saver.get_tuple(config)
        assert saved is not None
        assert "MIGRATED-STRATEGY" in repr(saved.checkpoint)
    backups = list(db.parent.glob("MSFT.db.plaintext.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes().startswith(b"SQLite format 3\x00")
    assert not db.read_bytes().startswith(b"SQLite format 3\x00")


def test_checkpoint_fails_closed_without_key(tmp_path: Path, monkeypatch) -> None:
    import core.trading.graph.checkpointer as checkpointer

    monkeypatch.setattr(
        checkpointer,
        "_get_db_key",
        lambda: (_ for _ in ()).throw(RuntimeError("no checkpoint key")),
    )
    with pytest.raises(RuntimeError, match="no checkpoint key"):
        with get_checkpointer(tmp_path, "AAPL"):
            pass
    db = tmp_path / "checkpoints" / "AAPL.db"
    assert not db.exists() or not db.read_bytes().startswith(b"SQLite format 3\x00")


def test_result_json_is_encrypted_decryptable_and_backs_up_plaintext(tmp_path: Path) -> None:
    marker = "PRIVATE-RESULT-DEBATE"
    graph = object.__new__(VectorTradingGraph)
    graph.ticker = "AAPL"
    graph.config = {"results_dir": str(tmp_path)}
    graph.log_states_dict = {}
    path = tmp_path / "AAPL" / "VectorTradingStrategy_logs" / "full_states_log_2026-10-08.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"legacy": "plaintext strategy"}', encoding="utf-8")

    graph._log_state("2026-10-08", _final_state(marker))

    raw = path.read_bytes()
    assert marker.encode() not in raw
    assert not raw.lstrip().startswith(b"{")
    assert json.loads(read_encrypted_text(path))["market_report"] == marker
    backups = list(path.parent.glob(f"{path.name}.plaintext.bak.*"))
    assert len(backups) == 1
    assert b"plaintext strategy" in backups[0].read_bytes()


def test_trading_memory_is_encrypted_decryptable_and_backs_up_plaintext(tmp_path: Path) -> None:
    marker = "PRIVATE-MEMORY-POSITION-SIZING"
    path = tmp_path / "trading_memory.md"
    legacy = "[2026-10-07 | AAPL | Hold | pending]\n\nDECISION:\nlegacy trading lesson\n\n<!-- ENTRY_END -->\n\n"
    path.write_text(legacy, encoding="utf-8")
    log = TradingMemoryLog({"memory_log_path": str(path)})

    log.store_decision("NVDA", "2026-10-08", f"Rating: Buy\n{marker}")

    raw = path.read_bytes()
    assert marker.encode() not in raw
    assert b"DECISION:" not in raw
    assert log.load_entries()[1]["decision"].endswith(marker)
    backups = list(tmp_path.glob("trading_memory.md.plaintext.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == legacy


def test_file_encryption_fails_closed_without_key(tmp_path: Path, monkeypatch) -> None:
    import core.trading.storage_crypto as crypto

    monkeypatch.setattr(crypto, "_get_shared_key", lambda: (_ for _ in ()).throw(RuntimeError("no key")))
    with pytest.raises(RuntimeError, match="no key"):
        TradingMemoryLog({"memory_log_path": str(tmp_path / "memory.md")}).store_decision(
            "AAPL", "2026-10-08", "Rating: Hold"
        )
    assert not (tmp_path / "memory.md").exists()


def test_result_writer_fails_closed_without_key(tmp_path: Path, monkeypatch) -> None:
    import core.trading.storage_crypto as crypto

    monkeypatch.setattr(crypto, "_get_shared_key", lambda: (_ for _ in ()).throw(RuntimeError("no key")))
    graph = object.__new__(VectorTradingGraph)
    graph.ticker = "AAPL"
    graph.config = {"results_dir": str(tmp_path)}
    graph.log_states_dict = {}
    with pytest.raises(RuntimeError, match="no key"):
        graph._log_state("2026-10-08", _final_state("sensitive"))
    assert not list(tmp_path.rglob("*.json"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
