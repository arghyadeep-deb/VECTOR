"""Compatibility shim; ``vectorcode.src.vc_security`` is canonical."""

from vectorcode.src.vc_security.credential_stripper import (
    CredentialStripper,
    wrap_tool_output,
)

__all__ = ["CredentialStripper", "wrap_tool_output"]
