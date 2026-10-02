"""Regression for vectorcode/src/vector_cli/vault_cmd.py's _load_vault():

it used to return {} on ANY decryption failure (wrong/corrupted key,
tampered or corrupted ciphertext) -- indistinguishable from a genuinely
empty vault. vault_set() would then happily _save_vault({key: value}),
silently destroying every other previously-stored credential. Fixed to
raise VaultDecryptionError instead, caught by every command (set/get/
list/remove) and shown as a clean error rather than propagating or
silently wiping data.
"""
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vector_cli import vault_cmd


@pytest.fixture
def isolated_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(vault_cmd, "_VAULT_FILE", tmp_path / "vault.enc")
    monkeypatch.setattr(vault_cmd, "_VAULT_KEY_FILE", tmp_path / ".vault_key")
    return tmp_path


def test_load_vault_raises_on_corrupt_ciphertext(isolated_vault):
    pytest.importorskip("cryptography")
    vault_cmd._get_or_create_key()
    vault_cmd._VAULT_FILE.write_bytes(b"not valid fernet ciphertext")
    with pytest.raises(vault_cmd.VaultDecryptionError):
        vault_cmd._load_vault()


def test_vault_set_does_not_wipe_vault_on_decrypt_failure(isolated_vault):
    pytest.importorskip("cryptography")
    vault_cmd._get_or_create_key()
    vault_cmd._VAULT_FILE.write_bytes(b"corrupt")
    runner = CliRunner()
    result = runner.invoke(vault_cmd.vault_set, ["mykey", "myvalue"])
    assert result.exit_code != 0
    # The corrupt file must be untouched -- not overwritten with {"mykey": "myvalue"}.
    assert vault_cmd._VAULT_FILE.read_bytes() == b"corrupt"


def test_vault_list_reports_clean_error_on_decrypt_failure(isolated_vault):
    pytest.importorskip("cryptography")
    vault_cmd._get_or_create_key()
    vault_cmd._VAULT_FILE.write_bytes(b"corrupt")
    runner = CliRunner()
    result = runner.invoke(vault_cmd.vault_list, [])
    assert "could not be decrypted" in result.output


def test_vault_remove_reports_clean_error_on_decrypt_failure(isolated_vault):
    pytest.importorskip("cryptography")
    vault_cmd._get_or_create_key()
    vault_cmd._VAULT_FILE.write_bytes(b"corrupt")
    runner = CliRunner()
    result = runner.invoke(vault_cmd.vault_remove, ["mykey"])
    assert "could not be decrypted" in result.output


def test_vault_roundtrip_still_works(isolated_vault):
    pytest.importorskip("cryptography")
    runner = CliRunner()
    r1 = runner.invoke(vault_cmd.vault_set, ["mykey", "myvalue"])
    assert r1.exit_code == 0
    r2 = runner.invoke(vault_cmd.vault_get, ["mykey"])
    assert r2.exit_code == 0
    assert "myvalue" in r2.output


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
