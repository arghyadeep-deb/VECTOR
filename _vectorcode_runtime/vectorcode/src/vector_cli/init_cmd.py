"""Legacy init command adapter."""

from __future__ import annotations

from vectorcode.src.cli.init_cmd import init


def init_command(**kwargs) -> None:
    """Run the init command callback for legacy callers."""
    init.callback(**kwargs)
