"""Regression test for a silently swallowed quota-ledger prune failure.

Malformed persisted day keys can make pruning fail. That failure used to be
discarded with ``except: pass``, hiding degraded quota accounting.
"""
from __future__ import annotations

from loguru import logger

from core.inference.quota_ledger import QuotaLedger


def test_prune_failure_is_logged(tmp_path):
    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        ledger = QuotaLedger(path=tmp_path / "quota.json")
        ledger._data = {object(): {}}
        ledger._prune()
    finally:
        logger.remove(sink)

    assert any("ledger prune failed" in message for message in messages)


if __name__ == "__main__":
    raise SystemExit("Run with: pytest tests/test_quota_ledger_failure_logging.py -v")
