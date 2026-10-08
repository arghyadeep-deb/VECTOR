"""VCSEC-6 regressions for attributable, fail-closed declassification."""
from __future__ import annotations

import json

import pytest

from vectorcode.src.vc_security.audit import AuditLogger
from vectorcode.src.vc_security.taint import TaintLabel, TaintSet, declassify


def test_declassify_records_all_required_fields_before_return(tmp_path) -> None:
    audit = AuditLogger(tmp_path / "audit.db")
    taint = TaintSet.from_labels(TaintLabel.SECRET, TaintLabel.EXTERNAL)
    try:
        result = declassify(
            taint,
            TaintLabel.SECRET,
            "owner approved export",
            actor="agent:privacy-guardian",
            source="tool:credential-store",
            destination="tool:channel-send",
            audit=audit,
        )
        event = audit.query(event_type="declassification", limit=1)[0]
    finally:
        audit.close()

    assert result.labels == frozenset({TaintLabel.EXTERNAL})
    assert json.loads(event.action_taken) == {
        "actor": "agent:privacy-guardian",
        "destination": "tool:channel-send",
        "label": "secret",
        "reason": "owner approved export",
        "source": "tool:credential-store",
    }


def test_declassify_fails_closed_when_audit_write_fails() -> None:
    class FailingAudit:
        def log_declassification(self, **kwargs) -> None:
            raise RuntimeError("audit unavailable")

    taint = TaintSet.from_labels(TaintLabel.PII)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        declassify(
            taint,
            TaintLabel.PII,
            "approved",
            actor="owner",
            source="input",
            destination="report",
            audit=FailingAudit(),
        )
    assert taint.has(TaintLabel.PII)


def test_declassify_rejects_blank_accountability_fields() -> None:
    taint = TaintSet.from_labels(TaintLabel.PII)
    with pytest.raises(ValueError, match="reason"):
        declassify(
            taint,
            TaintLabel.PII,
            " ",
            actor="owner",
            source="input",
            destination="report",
            audit=None,
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
