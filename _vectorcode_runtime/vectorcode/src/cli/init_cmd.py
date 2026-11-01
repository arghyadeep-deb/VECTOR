"""Click entry point for first-run VECTOR initialization."""

from __future__ import annotations

from types import SimpleNamespace

import click


@click.command()
@click.option("--quick", is_flag=True, help="Run the quick setup path.")
@click.option("--reset", is_flag=True, help="Reset config before setup.")
@click.option("--reconfigure", is_flag=True, help="Force full reconfiguration.")
@click.option("--non-interactive", is_flag=True, help="Print non-interactive guidance.")
@click.option("--from-bare-vector", is_flag=True, hidden=True)
@click.argument("section", required=False)
def init(
    section: str | None = None,
    quick: bool = False,
    reset: bool = False,
    reconfigure: bool = False,
    non_interactive: bool = False,
    from_bare_vector: bool = False,
) -> None:
    """Initialize VECTOR configuration via the setup wizard."""
    from vectorcode.src.vector_cli.setup import run_setup_wizard

    args = SimpleNamespace(
        section=section,
        quick=quick,
        reset=reset,
        reconfigure=reconfigure,
        non_interactive=non_interactive,
        from_bare_vector=from_bare_vector,
    )
    run_setup_wizard(args)
