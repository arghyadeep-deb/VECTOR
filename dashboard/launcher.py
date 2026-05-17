"""
VECTOR Desktop Launcher — Python-native desktop window.

Serves the React JARVIS UI via a local FastAPI server and wraps it in a
native desktop window using pywebview. Zero Rust, zero Electron.

Usage:
    python dashboard/launcher.py              # dev (Vite hot-reload)
    python dashboard/launcher.py --prod       # production (serves built /dist)
    python dashboard/launcher.py --port 7789  # custom port

Requirements:
    pip install pywebview fastapi uvicorn aiofiles
    npm install (in dashboard/)
    npm run build (for --prod mode)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VECTOR Desktop Launcher")
    p.add_argument("--prod", action="store_true", help="Serve built /dist instead of Vite dev server")
    p.add_argument("--port", type=int, default=7789, help="Port for the UI server (default 7789)")
    p.add_argument("--core-port", type=int, default=8000, help="VECTOR core WebSocket port")
    p.add_argument("--no-window", action="store_true", help="Headless mode (no desktop window)")
    p.add_argument("--debug", action="store_true", help="Enable pywebview debug panel")
    return p.parse_args()


def _start_prod_server(port: int, dist_dir: Path) -> threading.Thread:
    """Serve the built React /dist with FastAPI."""
    try:
        import uvicorn
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse

        app = FastAPI(title="VECTOR UI")
        app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # SPA fallback — always return index.html
            return FileResponse(dist_dir / "index.html")

        def _run():
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        logger.info("[VECTOR][launcher] prod server → http://127.0.0.1:{}", port)
        return t
    except ImportError as e:
        logger.error("[VECTOR][launcher] missing dep: {} — run: pip install fastapi uvicorn aiofiles", e)
        sys.exit(1)


def _start_vite_dev(port: int, dashboard_dir: Path) -> subprocess.Popen:
    """Start Vite dev server with hot-reload."""
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    proc = subprocess.Popen(
        [npm, "run", "dev", "--", "--port", str(port)],
        cwd=dashboard_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("[VECTOR][launcher] Vite dev server → http://127.0.0.1:{}", port)
    return proc


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """Poll until the UI server responds."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _open_window(url: str, debug: bool = False) -> None:
    """Open a native desktop window via pywebview."""
    try:
        import webview
    except ImportError:
        logger.error("[VECTOR][launcher] pywebview not installed — run: pip install pywebview")
        logger.info("[VECTOR][launcher] Opening in browser instead: {}", url)
        import webbrowser
        webbrowser.open(url)
        input("Press Enter to exit...")
        return

    window = webview.create_window(
        title="VECTOR — Virtual Entity for Cognitive Tasks & Operational Reasoning",
        url=url,
        width=1400,
        height=900,
        min_size=(1100, 700),
        background_color="#020A14",   # JARVIS dark background
        frameless=False,              # set True for borderless JARVIS look
        easy_drag=True,
        text_select=False,
    )

    logger.info("[VECTOR][launcher] desktop window opened")
    webview.start(debug=debug, http_server=False)


def main() -> None:
    args = _parse_args()
    dashboard_dir = Path(__file__).parent
    dist_dir = dashboard_dir / "dist"
    url = f"http://127.0.0.1:{args.port}"

    logger.info("[VECTOR][launcher] starting VECTOR desktop app (prod={})", args.prod)

    proc = None

    if args.prod:
        if not dist_dir.exists():
            logger.error("[VECTOR][launcher] /dist not found — run: cd dashboard && npm run build")
            sys.exit(1)
        _start_prod_server(args.port, dist_dir)
    else:
        # Check node_modules
        if not (dashboard_dir / "node_modules").exists():
            logger.info("[VECTOR][launcher] running npm install...")
            npm = "npm.cmd" if sys.platform == "win32" else "npm"
            subprocess.run([npm, "install"], cwd=dashboard_dir, check=True)
        proc = _start_vite_dev(args.port, dashboard_dir)

    # Wait for server to be ready
    logger.info("[VECTOR][launcher] waiting for UI server...")
    if not _wait_for_server(args.port):
        logger.error("[VECTOR][launcher] UI server did not start within timeout")
        if proc:
            proc.terminate()
        sys.exit(1)

    logger.info("[VECTOR][launcher] UI ready at {}", url)

    if args.no_window:
        logger.info("[VECTOR][launcher] headless mode — UI at {}", url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        _open_window(url, debug=args.debug)

    # Cleanup
    if proc:
        proc.terminate()
    logger.info("[VECTOR][launcher] shutdown")


if __name__ == "__main__":
    main()
