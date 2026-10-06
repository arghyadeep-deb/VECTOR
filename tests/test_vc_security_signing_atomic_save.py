"""Regression for vectorcode/src/vc_security/signing.py's save_keypair():

Wrote the private/public key files directly with write_text() -- not
atomic, so a crash mid-write (or a failed os.replace) could corrupt or
truncate the private key, and the private key file got default OS
permissions instead of 0o600 like every other credential file fixed this
audit cycle (vault_cmd.py, mcp_oauth.py, etc).
"""
from __future__ import annotations

import os
import stat
import sys

import pytest

from vectorcode.src.vc_security.signing import KeyPair, save_keypair


def test_save_keypair_private_key_survives_a_failed_replace(tmp_path, monkeypatch):
    keypair = KeyPair(private_key=b"\x00" * 32, public_key=b"\x01" * 32)
    priv = tmp_path / "key.priv"
    pub = tmp_path / "key.pub"
    priv.write_text("original", encoding="utf-8")

    def fail_replace(_src, _dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(
        "vectorcode.src.vc_security.signing.os.replace", fail_replace
    )

    with pytest.raises(OSError, match="simulated replace failure"):
        save_keypair(keypair, str(priv), str(pub))

    assert priv.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(".key.priv.*.tmp")) == []


def test_save_keypair_restricts_private_key_permissions(tmp_path):
    keypair = KeyPair(private_key=b"\x02" * 32, public_key=b"\x03" * 32)
    priv = tmp_path / "key.priv"
    pub = tmp_path / "key.pub"

    save_keypair(keypair, str(priv), str(pub))

    assert priv.exists()
    assert pub.exists()
    if sys.platform != "win32":
        mode = stat.S_IMODE(os.stat(priv).st_mode)
        assert mode == 0o600
