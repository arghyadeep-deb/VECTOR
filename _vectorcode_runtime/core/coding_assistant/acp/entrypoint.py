from __future__ import annotations


import logging

logger = logging.getLogger(__name__)

__all__ = [
    "Arguments",
    "bootstrap_config_files",
    "handle_debug_mode",
    "main",
    "parse_arguments",
]


import argparse
from dataclasses import dataclass
import os
import sys

import tomli_w

from core.coding_assistant import __version__
from core.coding_assistant.core.config import VectorCAConfig
from core.coding_assistant.core.config.harness_files import (
    get_harness_files_manager,
    init_harness_files_manager,
)
from core.coding_assistant.core.logger import logger
from core.coding_assistant.core.paths import HISTORY_FILE
# [VECTOR] telemetry removed: from core.coding_assistant.core.telemetry.build_metadata import build_entrypoint_metadata

# Configure line buffering for subprocess communication
sys.stdout.reconfigure(line_buffering=True)  # pyright: ignore[reportAttributeAccessIssue]
sys.stderr.reconfigure(line_buffering=True)  # pyright: ignore[reportAttributeAccessIssue]
sys.stdin.reconfigure(line_buffering=True)  # pyright: ignore[reportAttributeAccessIssue]


@dataclass
class Arguments:
    setup: bool


def parse_arguments() -> Arguments:
    parser = argparse.ArgumentParser(description="Run VECTOR Coding Assistant in ACP mode")
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("--setup", action="store_true", help="Setup API key and exit")
    args = parser.parse_args()
    return Arguments(setup=args.setup)


def bootstrap_config_files() -> None:
    mgr = get_harness_files_manager()
    config_file = mgr.user_config_file
    if not config_file.exists():
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            with config_file.open("wb") as f:
                tomli_w.dump(VectorCAConfig.create_default(), f)
        except Exception as e:
            logger.error(f"Could not create default config file: {e}")
            raise

    history_file = HISTORY_FILE.path
    if not history_file.exists():
        try:
            history_file.parent.mkdir(parents=True, exist_ok=True)
            history_file.write_text("Hello Vibe!\n", "utf-8")
        except Exception as e:
            logger.error(f"Could not create history file: {e}")
            raise


# When DEBUG_MODE=true, attaches debugpy on localhost:5678.
def handle_debug_mode() -> None:
    if os.environ.get("DEBUG_MODE") != "true":
        return

    try:
        import debugpy
    except ImportError:
        return

    debugpy.listen(("localhost", 5678))
    # uncomment this to wait for the debugger to attach
    # debugpy.wait_for_client()


def main() -> None:
    handle_debug_mode()
    init_harness_files_manager("user", "project")

    from core.coding_assistant.acp.acp_agent_loop import run_acp_server
    from core.coding_assistant.core.config import VectorCAConfig, load_dotenv_values
# [VECTOR] removed:     from core.coding_assistant.core.tracing import setup_tracing
    from core.coding_assistant.setup.onboarding import run_onboarding

    load_dotenv_values()
    bootstrap_config_files()
    args = parse_arguments()
    if args.setup:
        run_onboarding(
            entrypoint_metadata=build_entrypoint_metadata(
                agent_entrypoint="acp",
                agent_version=__version__,
                client_name="vibe_acp",
                client_version=__version__,
            )
        )
        sys.exit(0)

    try:
        config = VectorCAConfig.load()
    except Exception:
        logger.exception("[VECTOR] silent swallow")
        pass  # tracing disabled

    run_acp_server()


if __name__ == "__main__":
    main()
