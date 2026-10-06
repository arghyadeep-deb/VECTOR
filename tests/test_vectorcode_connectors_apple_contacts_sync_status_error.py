"""Regression for vectorcode/src/connectors/apple_contacts.py:

Same bug shape as the oura/weather/hackernews/granola/apple_notes/imessage
fixes: SyncStatus.state defaults to "idle", which is also the value a
successful sync() leaves it at, and sync() never wrapped its query/iteration
body in try/except. A mid-sync exception (locked DB, missing table from a
macOS schema change) left sync_status() permanently reporting state="idle"
with no error -- indistinguishable from "nothing synced yet".

Fixed: sync() now tracks self._state/self._last_error, setting them to
"error"/str(exc) on exception (re-raised unchanged) and "idle"/None on
success; sync_status() surfaces them.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from vectorcode.src.connectors.apple_contacts import AppleContactsConnector


def _make_broken_db(path: Path) -> None:
    # A real, openable SQLite file missing the ZABCDRECORD table the
    # connector's SELECT expects -- triggers sqlite3.OperationalError from
    # *inside* the try block (query execution), not from connect() itself.
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()


def test_apple_contacts_sync_failure_reports_error_status(tmp_path):
    db_path = tmp_path / "AddressBook-v22.abcddb"
    _make_broken_db(db_path)
    connector = AppleContactsConnector(db_path=str(db_path))

    assert connector.sync_status().state == "idle"
    assert connector.sync_status().error is None

    with pytest.raises(sqlite3.OperationalError):
        list(connector.sync())

    status = connector.sync_status()
    assert status.state == "error"
    assert status.error is not None


def test_apple_contacts_sync_success_clears_prior_error(tmp_path):
    db_path = tmp_path / "AddressBook-v22.abcddb"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE ZABCDRECORD (Z_PK INTEGER PRIMARY KEY, ZFIRSTNAME TEXT, "
        "ZMIDDLENAME TEXT, ZLASTNAME TEXT, ZORGANIZATION TEXT, ZJOBTITLE TEXT, "
        "ZDEPARTMENT TEXT, ZNICKNAME TEXT, ZBIRTHDAY REAL, ZCREATIONDATE REAL, "
        "ZMODIFICATIONDATE REAL, ZUNIQUEID TEXT)"
    )
    conn.execute(
        "INSERT INTO ZABCDRECORD VALUES (1, 'Ada', NULL, 'Lovelace', NULL, "
        "NULL, NULL, NULL, NULL, 0.0, 0.0, 'uid-1')"
    )
    for table in (
        "ZABCDPHONENUMBER(ZFULLNUMBER TEXT, ZLABEL TEXT, ZOWNER INTEGER, ZORDERINGINDEX INTEGER)",
        "ZABCDEMAILADDRESS(ZADDRESS TEXT, ZLABEL TEXT, ZOWNER INTEGER, ZORDERINGINDEX INTEGER)",
        "ZABCDPOSTALADDRESS(ZSTREET TEXT, ZCITY TEXT, ZSTATE TEXT, ZZIPCODE TEXT, "
        "ZCOUNTRYNAME TEXT, ZLABEL TEXT, ZOWNER INTEGER, ZORDERINGINDEX INTEGER)",
        "ZABCDURLADDRESS(ZURL TEXT, ZLABEL TEXT, ZOWNER INTEGER, ZORDERINGINDEX INTEGER)",
        "ZABCDSOCIALPROFILE(ZUSERNAME TEXT, ZSERVICENAME TEXT, ZLABEL TEXT, ZOWNER INTEGER, ZORDERINGINDEX INTEGER)",
        "ZABCDNOTE(ZTEXT TEXT, ZCONTACT INTEGER)",
    ):
        conn.execute(f"CREATE TABLE {table}")
    conn.commit()
    conn.close()

    connector = AppleContactsConnector(db_path=str(db_path))
    docs = list(connector.sync())

    assert len(docs) == 1
    status = connector.sync_status()
    assert status.state == "idle"
    assert status.error is None
    assert status.items_synced == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
