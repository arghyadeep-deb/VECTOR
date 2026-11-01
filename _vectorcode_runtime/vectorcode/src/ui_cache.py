"""Prepare the terminal's production dependencies in writable user storage."""

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from loguru import logger

_READY_FILE = ".vectorcode-ui-ready.json"


def _check_path(path: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise SystemExit("Terminal UI paths must not contain symbolic links or junctions.")


def source_ui() -> Path:
    return Path(__file__).resolve().parents[1] / "packages" / "cli"


def ui_files(source: Path) -> list[Path]:
    """Return only production JavaScript and its pinned npm metadata."""
    source = Path(source).absolute()
    _check_path(source)
    _check_path(source / "dist")
    files = [source / "package.json", source / "package-lock.json"]
    files.extend(
        path for path in (source / "dist").rglob("*.js")
        if "__tests__" not in path.relative_to(source).parts
        and not path.name.endswith((".test.js", ".spec.js"))
    )
    if not (source / "dist" / "index.js").is_file() or any(not path.is_file() for path in files):
        raise SystemExit("Terminal UI artifact is incomplete. Rebuild the terminal UI before packaging.")
    for path in files:
        _check_path(path)
        if not path.resolve().is_relative_to(source.resolve()):
            raise SystemExit("Terminal UI artifact escapes its package directory.")
    return sorted(files, key=lambda path: path.relative_to(source).as_posix())


def _content_hash(source: Path) -> str:
    digest = hashlib.sha256()
    for path in ui_files(source):
        relative = path.relative_to(source).as_posix().encode("utf-8")
        contents = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big") + relative)
        digest.update(len(contents).to_bytes(8, "big") + contents)
    return digest.hexdigest()


def cache_path(source: Path | None = None, cache_root: Path | None = None) -> Path:
    source = Path(source or source_ui()).absolute()
    content_hash = _content_hash(source)
    if cache_root is None:
        from core.config import CONFIG

        cache_root = Path(CONFIG["vectorcode"]["ui_cache_dir"])
    cache_root = Path(cache_root).expanduser().absolute()
    _check_path(cache_root)
    target = cache_root / content_hash
    _check_path(target)
    if target.resolve().parent != cache_root.resolve():
        raise SystemExit("Terminal UI cache destination escapes its configured root.")
    if target.resolve().is_relative_to(source.resolve()):
        raise SystemExit("Terminal UI cache must be outside the installed UI package.")
    return target.resolve()


def require_node() -> str:
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js 24 or newer is required for the terminal UI.")
    try:
        result = subprocess.run([node, "--version"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("Could not check Node.js 24 or newer; check your Node installation.") from exc
    match = re.fullmatch(r"v?(\d+)\.\d+\.\d+(?:[-+][\w.-]+)?", result.stdout.strip())
    if not match or int(match.group(1)) < 24:
        raise SystemExit("Node.js 24 or newer is required for the terminal UI.")
    return node


def check_dependencies(node: str, target: Path) -> None:
    """Load the locked UI dependencies without rendering, inference or network setup."""
    from core.config import CONFIG

    _check_path(target)
    try:
        subprocess.run(
            [node, "--input-type=module", "--eval", "await import('ink'); await import('react');"],
            cwd=target, check=True, capture_output=True, text=True,
            timeout=CONFIG["vectorcode"]["ui_probe_timeout_sec"],
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise SystemExit(
            "Terminal UI dependencies could not load. Run vector setup-ui to repair them. "
            "On Windows, set VECTORCODE__UI_CACHE_DIR to a shorter writable path "
            "before setup and launch if the cache path is too long."
        ) from None


def is_ready(target: Path) -> bool:
    try:
        target = Path(target).absolute()
        _check_path(target)
        _check_path(target / "node_modules" / "ink")
        _check_path(target / _READY_FILE)
        metadata = json.loads((target / _READY_FILE).read_text(encoding="utf-8"))
        return (
            metadata == {"content_hash": target.name}
            and _content_hash(target) == target.name
            and (target / "dist" / "index.js").is_file()
            and (target / "node_modules" / "ink").is_dir()
        )
    except (OSError, ValueError, SystemExit):
        return False


def prepare_ui(source: Path | None = None, cache_root: Path | None = None) -> Path:
    """Explicitly install locked production npm dependencies; never called by launch."""
    source = Path(source or source_ui()).absolute()
    files = ui_files(source)
    node = require_node()
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("npm is required. Install Node.js 24 or newer, then run vector setup-ui.")
    target = cache_path(source, cache_root)
    marker = target / _READY_FILE
    _check_path(marker)
    if is_ready(target):
        try:
            check_dependencies(node, target)
        except SystemExit:
            marker.unlink(missing_ok=True)
            raise
        logger.info("[VECTOR][terminal] UI dependencies already prepared in {}", target)
        return target
    target.mkdir(parents=True, exist_ok=True)
    _check_path(target / "node_modules")
    marker.unlink(missing_ok=True)
    for path in files:
        destination = target / path.relative_to(source)
        _check_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    expected = {path.relative_to(source) for path in files}
    unexpected = [path for path in ui_files(target) if path.relative_to(target) not in expected]
    for path in unexpected:
        _check_path(path)
        if path.suffix != ".js" or not path.resolve().is_relative_to((target / "dist").resolve()):
            raise SystemExit("Terminal UI cache cleanup must stay inside its compiled JavaScript directory.")
        path.unlink()
    try:
        subprocess.run(
            [npm, "ci", "--omit=dev", "--ignore-scripts", "--workspaces=false"],
            cwd=target, check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("Terminal UI npm setup failed. Run vector setup-ui to retry.") from exc
    if not (target / "node_modules" / "ink").is_dir():
        raise SystemExit("Terminal UI npm setup failed: Ink was not installed. Run vector setup-ui to retry.")
    check_dependencies(node, target)
    marker.write_text(json.dumps({"content_hash": target.name}), encoding="utf-8")
    if not is_ready(target):
        _check_path(marker)
        marker.unlink(missing_ok=True)
        raise SystemExit("Terminal UI cache verification failed. Run vector setup-ui to retry.")
    logger.info("[VECTOR][terminal] UI dependencies prepared in {}", target)
    return target


if __name__ == "__main__":
    assert source_ui().is_dir()
