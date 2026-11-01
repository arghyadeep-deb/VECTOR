from __future__ import annotations

from core.coding_assistant.core.auth.crypto import EncryptedPayload, decrypt, encrypt

# GitHubAuthProvider removed — VECTOR uses gh CLI for GitHub auth
class GitHubAuthProvider:
    """Stub — GitHub OAuth removed; VECTOR uses gh CLI."""
    pass

__all__ = ["EncryptedPayload", "GitHubAuthProvider", "decrypt", "encrypt"]
