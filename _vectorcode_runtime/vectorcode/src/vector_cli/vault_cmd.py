"""``vector vault`` — encrypted credential store."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import click
from rich.console import Console
from rich.table import Table

from vectorcode.src.core.config import DEFAULT_CONFIG_DIR

_VAULT_FILE = DEFAULT_CONFIG_DIR / "vault.enc"
_VAULT_KEY_FILE = DEFAULT_CONFIG_DIR / ".vault_key"


def _get_or_create_key() -> bytes:
    """Get or create a Fernet encryption key."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise ImportError(
            "cryptography not installed. Install with: uv sync --extra security-signing"
        )

    if _VAULT_KEY_FILE.exists():
        return _VAULT_KEY_FILE.read_bytes().strip()

    key = Fernet.generate_key()
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _VAULT_KEY_FILE.write_bytes(key)
    _VAULT_KEY_FILE.chmod(0o600)
    return key


class VaultDecryptionError(Exception):
    """Vault file exists but could not be decrypted (wrong/corrupted key,
    tampered or corrupted ciphertext). Distinct from "no vault file yet"
    so a caller never mistakes a real decrypt failure for an empty vault --
    vault_set() would otherwise silently overwrite (and destroy) every
    existing credential on the next save."""


def _load_vault() -> dict:
    """Load and decrypt vault contents.

    Raises VaultDecryptionError if the vault file exists but cannot be
    decrypted -- returning {} here previously made vault_set() silently
    wipe every stored credential on the very next save whenever decryption
    failed for any reason (wrong/corrupted key, tampered or corrupted
    ciphertext), indistinguishable from a genuinely empty vault.
    """
    if not _VAULT_FILE.exists():
        return {}
    from cryptography.fernet import Fernet

    key = _get_or_create_key()
    f = Fernet(key)
    encrypted = _VAULT_FILE.read_bytes()
    try:
        decrypted = f.decrypt(encrypted)
    except Exception as e:
        raise VaultDecryptionError(
            f"Vault file exists but could not be decrypted: {e}. "
            "Refusing to treat this as an empty vault to avoid overwriting "
            "existing credentials."
        ) from e
    return json.loads(decrypted.decode())


def _save_vault(data: dict) -> None:
    """Encrypt and save vault contents."""
    from cryptography.fernet import Fernet

    key = _get_or_create_key()
    f = Fernet(key)
    plaintext = json.dumps(data).encode()
    encrypted = f.encrypt(plaintext)
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{_VAULT_FILE.name}.", suffix=".tmp", dir=str(_VAULT_FILE.parent)
    )
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(encrypted)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, _VAULT_FILE)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


@click.group()
def vault() -> None:
    """Manage encrypted credentials."""


@vault.command("set")
@click.argument("key")
@click.argument("value")
def vault_set(key: str, value: str) -> None:
    """Store a credential in the vault."""
    console = Console(stderr=True)
    try:
        data = _load_vault()
        data[key] = value
        _save_vault(data)
        console.print(f"[green]Stored credential: {key}[/green]")
    except (ImportError, VaultDecryptionError) as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


@vault.command("get")
@click.argument("key")
def vault_get(key: str) -> None:
    """Retrieve a credential from the vault."""
    console = Console(stderr=True)
    try:
        data = _load_vault()
        if key in data:
            console.print(data[key])
        else:
            console.print(f"[yellow]Key not found: {key}[/yellow]")
    except (ImportError, VaultDecryptionError) as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)


@vault.command("list")
def vault_list() -> None:
    """List all stored credential keys."""
    console = Console(stderr=True)
    try:
        data = _load_vault()
        if not data:
            console.print("[dim]Vault is empty.[/dim]")
            return
        table = Table(title="Vault Keys")
        table.add_column("Key", style="cyan")
        table.add_column("Value Preview", style="dim")
        for k, v in sorted(data.items()):
            preview = v[:4] + "****" if len(v) > 4 else "****"
            table.add_row(k, preview)
        console.print(table)
    except (ImportError, VaultDecryptionError) as exc:
        console.print(f"[red]{exc}[/red]")


@vault.command("remove")
@click.argument("key")
def vault_remove(key: str) -> None:
    """Remove a credential from the vault."""
    console = Console(stderr=True)
    try:
        data = _load_vault()
        if key in data:
            del data[key]
            _save_vault(data)
            console.print(f"[green]Removed: {key}[/green]")
        else:
            console.print(f"[yellow]Key not found: {key}[/yellow]")
    except (ImportError, VaultDecryptionError) as exc:
        console.print(f"[red]{exc}[/red]")


__all__ = ["vault"]
