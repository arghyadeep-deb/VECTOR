"""Launch the compiled terminal UI while preserving the existing one-shot CLI."""

import os
import subprocess
import sys
from pathlib import Path

from vectorcode.src.ui_cache import cache_path, check_dependencies, is_ready, require_node, source_ui


def launch_tui(args, *, ui_root=None):
    node = require_node()
    root = Path(ui_root) if ui_root is not None else source_ui()
    entry = root / "dist" / "index.js"
    if not entry.is_file() or not (root / "node_modules" / "ink").is_dir():
        root = cache_path(root)
        entry = root / "dist" / "index.js"
        if not is_ready(root):
            raise SystemExit(
                "Terminal UI dependencies are not prepared. Run vector setup-ui with Node.js 24 or newer."
            )
    if not entry.is_file():
        raise SystemExit(
            "Terminal UI artifact is incomplete. Rebuild the terminal UI before packaging."
        )
    check_dependencies(node, root)
    command = [node, str(entry), "--python", sys.executable]
    if getattr(args, "model", None):
        command.extend(["--model", args.model])
    if getattr(args, "mode", None):
        command.extend(["--mode", args.mode])
    if getattr(args, "resume", None):
        command.extend(["--resume", str(args.resume)])
    if getattr(args, "editor_context_file", None):
        command.extend(["--editor-context-file", str(Path(args.editor_context_file).resolve())])
    project = Path(getattr(args, "dir", None) or Path.cwd()).resolve()
    if not project.is_dir():
        raise SystemExit("Project directory does not exist.")
    environment = dict(
        os.environ, VECTOR_PYTHON=sys.executable,
        VECTOR_CODING_ROOT=str(Path(__file__).resolve().parents[2]),
    )
    if "NO_COLOR" not in environment and environment.get("TERM") != "dumb":
        environment.setdefault("FORCE_COLOR", "3")
    return subprocess.run(command, cwd=project, env=environment).returncode


if __name__ == "__main__":
    assert Path(__file__).resolve().parents[1].is_dir()
