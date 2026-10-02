"""``jarvis gateway start|stop|status|logs`` — multi-channel gateway management."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click


@click.group()
def gateway() -> None:
    """Manage the OpenVector multi-channel gateway."""


@gateway.command()
@click.option(
    "--install",
    is_flag=True,
    help="Generate and enable systemd/launchd service",
)
def start(install: bool) -> None:
    """Start the gateway daemon."""
    if install:
        import platform as plat

        from vectorcode.src.daemon.service import (
            generate_launchd_plist,
            generate_systemd_service,
        )

        if plat.system() == "Darwin":
            plist_path = (
                Path.home() / "Library/LaunchAgents/com.openjarvis.gateway.plist"
            )
            generate_launchd_plist(plist_path)
            click.echo(f"Wrote {plist_path}")
            subprocess.run(
                ["launchctl", "load", str(plist_path)],
                check=False,
            )
        else:
            service_path = (
                Path.home() / ".config/systemd/user/openjarvis-gateway.service"
            )
            generate_systemd_service(service_path)
            click.echo(f"Wrote {service_path}")
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=False,
            )
            subprocess.run(
                ["systemctl", "--user", "enable", "--now", "openjarvis-gateway"],
                check=False,
            )
    else:
        # Phantom success: this branch printed "Gateway started." without
        # ever starting anything -- no subprocess, no blocking loop, no
        # real action at all. Dormant today (this `gateway` click group is
        # not registered anywhere in the real CLI, confirmed via
        # repo-wide grep), fixed anyway per this cycle's "fix narrow bugs
        # even in dormant code" bar, consistent with vectorcode/src/tools/
        # worktree.py and direct_executor.py's fixes.
        click.echo(
            "Foreground gateway start is not implemented here. "
            "Use --install to register a systemd/launchd service instead."
        )
        raise SystemExit(1)


@gateway.command()
def stop() -> None:
    """Stop the gateway daemon."""
    import platform as plat

    if plat.system() == "Darwin":
        subprocess.run(
            ["launchctl", "remove", "com.openjarvis.gateway"],
            check=False,
        )
    else:
        subprocess.run(
            ["systemctl", "--user", "stop", "openjarvis-gateway"],
            check=False,
        )
    click.echo("Gateway stopped.")


@gateway.command()
def status() -> None:
    """Check gateway status."""
    import platform as plat

    if plat.system() == "Darwin":
        subprocess.run(
            ["launchctl", "list", "com.openjarvis.gateway"],
            check=False,
        )
    else:
        subprocess.run(
            ["systemctl", "--user", "status", "openjarvis-gateway"],
            check=False,
        )


@gateway.command()
def logs() -> None:
    """View gateway logs."""
    import platform as plat

    if plat.system() == "Darwin":
        click.echo("Check ~/Library/Logs/com.openjarvis.gateway.log")
    else:
        subprocess.run(
            ["journalctl", "--user", "-u", "openjarvis-gateway", "-f"],
            check=False,
        )
