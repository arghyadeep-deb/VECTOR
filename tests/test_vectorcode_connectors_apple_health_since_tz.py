"""Regression for vectorcode/src/connectors/apple_health.py:

_sync_export_xml() filtered records with
``start_dt.replace(tzinfo=None) < since.replace(tzinfo=None)`` -- stripping
tzinfo from both sides before comparing. Apple Health export records carry
their own UTC offset (e.g. "-0500") which can differ from the caller's
``since`` offset (e.g. UTC, as SyncEngine's checkpoint stores it). Comparing
the raw wall-clock numbers instead of real instants silently mis-included or
mis-excluded records near the incremental-sync cutoff by up to the offset
difference (confirmed: a record at 2024-01-01 00:00:00 -0500, which is
2024-01-01 05:00:00 UTC, was incorrectly treated as BEFORE a 2024-01-01
02:00:00 UTC cutoff, even though the record is actually two hours AFTER it).

Fixed with a timezone-safe helper, _is_before(), used at both the Record and
Workout since-filter sites.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.connectors.apple_health import AppleHealthConnector

_EXPORT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
<Record type="HKQuantityTypeIdentifierStepCount" startDate="2024-01-01 00:00:00 -0500" endDate="2024-01-01 00:01:00 -0500" value="100" />
</HealthData>
"""


def test_since_filter_compares_real_instants_not_naive_wallclock(tmp_path):
    export_path = tmp_path / "export.xml"
    export_path.write_text(_EXPORT_XML, encoding="utf-8")

    connector = AppleHealthConnector(
        export_path=str(export_path),
        healthkit_db_path=str(tmp_path / "does-not-exist.sqlite"),
    )

    # The record is at 2024-01-01 00:00:00 -0500 == 2024-01-01 05:00:00 UTC.
    # A cutoff of 2024-01-01 02:00:00 UTC is BEFORE the record's real
    # instant, so the record must be included (synced), not skipped.
    since = datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc)
    docs = list(connector.sync(since=since))

    assert len(docs) == 1, (
        "record at 2024-01-01 00:00 -0500 (05:00 UTC) must not be skipped "
        "by a 02:00 UTC cutoff -- it is chronologically after it"
    )


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
