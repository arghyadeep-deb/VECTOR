from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OUT = ROOT / "test_tmp" / "frontend-captures"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def serve_frontend() -> tuple[socketserver.TCPServer, str]:
    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(FRONTEND), **kwargs)
    server = ReusableTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def capture() -> dict[str, object]:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {"captures": [], "errors": []}
    server, base = serve_frontend()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            scenarios = [
                ("dev-desktop", "/VECTOR.html", 1440, 900),
                ("dev-mobile", "/VECTOR.html", 390, 844),
            ]
            for name, path, width, height in scenarios:
                page_errors: list[str] = []
                console_errors: list[str] = []
                page = browser.new_page(viewport={"width": width, "height": height})
                page.route("**/*", lambda route: route.abort() if route.request.url.startswith(("http://", "https://")) and "127.0.0.1" not in route.request.url else route.continue_())
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.goto(base + path, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5200)
                png = OUT / f"{name}-ready.png"
                page.screenshot(path=str(png), full_page=True)
                page.locator("#stage").click(position={"x": width / 2, "y": height / 2})
                page.wait_for_timeout(900)
                awake_png = OUT / f"{name}-awake.png"
                page.screenshot(path=str(awake_png), full_page=True)
                stage = page.locator("#stage")
                box = stage.bounding_box() if stage.count() else None
                local_console_errors = [
                    err for err in console_errors
                    if err.strip() != "Failed to load resource: net::ERR_FAILED"
                ]
                results["captures"].append(
                    {
                        "name": name,
                        "url": base + path,
                        "screenshot": str(png),
                        "awake_screenshot": str(awake_png),
                        "page_errors": page_errors,
                        "console_errors": console_errors,
                        "local_console_errors": local_console_errors,
                        "stage_box": box,
                        "has_demo": page.locator('script[src="js/demo.js"]').count() > 0,
                        "has_director": page.locator("#director").count() > 0,
                    }
                )
                page.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture VECTOR frontend screenshots")
    parser.parse_args()
    result = capture()
    print(json.dumps(result, indent=2))
    has_errors = any(c["page_errors"] or c["local_console_errors"] for c in result["captures"])
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
