"""Core credentials shim — re-exports from vc_core.credentials.

This directory is documented (see __init__.py, "Gap 11") as a shim that
re-exports vc_core/ -- every sibling file here (config.py, events.py,
registry.py, types.py) does exactly that. This file didn't: it defined
its own, disconnected TOOL_CREDENTIALS = {} (always empty, never written
to the real ~/.vector/credentials.toml) and a get_credential_status()
that unconditionally returned the literal string "unknown" -- not the
dict[str, bool] the real vc_core.credentials.get_credential_status()
returns and that the one real caller (vector_cli/serve.py) iterates with
.values(). Because this shim's TOOL_CREDENTIALS was always empty, the
caller's `for tool in sorted(TOOL_CREDENTIALS): get_credential_status(tool)`
loop never actually ran the broken status call -- but it also meant the
startup "Credentials loaded" status log was permanently a no-op,
regardless of what credentials were really configured.
"""
from vectorcode.src.vc_core.credentials import (
    TOOL_CREDENTIALS,
    load_credentials,
    save_credential,
    get_credential_status,
    inject_credentials,
    get_tool_credential,
)
