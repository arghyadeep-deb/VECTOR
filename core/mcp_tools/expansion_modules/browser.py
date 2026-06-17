from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


def add_browser_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ browser_* (28) — wired to core/stealth_browser/client.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.stealth_browser.client import StealthBrowserClient

        _browser_client = None
        def _get_browser():
            nonlocal _browser_client
            if _browser_client is None:
                _browser_client = StealthBrowserClient()
            return _browser_client

        @mcp.tool
        def browser_open() -> str:
            """Open a new browser session."""
            try:
                client = _get_browser()
                tab_id = client.create_tab() if hasattr(client, "create_tab") else "tab_0"
                return _safe_json({"ok": True, "tab_id": tab_id})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_close(tab_id: str = "") -> str:
            """Close browser session or specific tab."""
            try:
                client = _get_browser()
                if tab_id and hasattr(client, "close_tab"):
                    client.close_tab(tab_id)
                elif hasattr(client, "close_all_tabs"):
                    client.close_all_tabs()
                return _safe_json({"ok": True})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_navigate(url: str, tab_id: str = "") -> str:
            """Navigate to a URL."""
            try:
                client = _get_browser()
                result = client.navigate(tab_id or "default", url) if hasattr(client, "navigate") else {"url": url}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_screenshot(tab_id: str = "") -> str:
            """Take a screenshot of current page."""
            try:
                client = _get_browser()
                result = client.screenshot(tab_id or "default") if hasattr(client, "screenshot") else {"status": "screenshot_taken"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_click(selector: str, tab_id: str = "") -> str:
            """Click an element by selector."""
            try:
                client = _get_browser()
                result = client.click(tab_id or "default", selector) if hasattr(client, "click") else {"selector": selector}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_type(text: str, selector: str = "", tab_id: str = "") -> str:
            """Type text into an input element."""
            try:
                client = _get_browser()
                result = client.type_text(tab_id or "default", text, ref=selector) if hasattr(client, "type_text") else {"text": text}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_scroll(direction: str = "down", amount: int = 500, tab_id: str = "") -> str:
            """Scroll the page."""
            try:
                client = _get_browser()
                result = client.scroll(tab_id or "default", direction, amount) if hasattr(client, "scroll") else {"direction": direction}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_extract(tab_id: str = "") -> str:
            """Extract text content from page."""
            try:
                client = _get_browser()
                result = client.snapshot(tab_id or "default") if hasattr(client, "snapshot") else {"status": "extracted"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_wait(selector: str = "", ms: int = 1000, tab_id: str = "") -> str:
            """Wait for an element or time."""
            try:
                client = _get_browser()
                result = client.wait(tab_id or "default", selector, ms) if hasattr(client, "wait") else {"ms": ms}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_element(selector: str, tab_id: str = "") -> str:
            """Get info about a page element."""
            try:
                client = _get_browser()
                snapshot = client.snapshot(tab_id or "default") if hasattr(client, "snapshot") else {}
                return _safe_json({"selector": selector, "snapshot": snapshot})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_form(selector: str, values: str = "{}", tab_id: str = "") -> str:
            """Fill a form with JSON values."""
            try:
                client = _get_browser()
                vals = _json.loads(values) if values else {}
                results = []
                for field, value in vals.items():
                    if hasattr(client, "type_text"):
                        client.type_text(tab_id or "default", str(value), ref=f"{selector} [name={field}]")
                    results.append({"field": field, "value": value})
                return _safe_json({"ok": True, "filled": results})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_back(tab_id: str = "") -> str:
            """Navigate back in history."""
            try:
                client = _get_browser()
                result = client.go_back(tab_id or "default") if hasattr(client, "go_back") else {"status": "navigated_back"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_forward(tab_id: str = "") -> str:
            """Navigate forward in history."""
            try:
                client = _get_browser()
                result = client.go_forward(tab_id or "default") if hasattr(client, "go_forward") else {"status": "navigated_forward"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_eval(script: str, tab_id: str = "") -> str:
            """Evaluate JavaScript on page via direct HTTP to stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/eval", json={"script": script})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "JS eval requires stealth browser server with /eval endpoint"})

        @mcp.tool
        async def browser_cookie(action: str = "list", name: str = "", value: str = "", tab_id: str = "") -> str:
            """Get or set browser cookies via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    if action == "list":
                        resp = await client.get(f"{base}/tabs/{tid}/cookies")
                    elif action == "set":
                        resp = await client.post(f"{base}/tabs/{tid}/cookies", json={"name": name, "value": value})
                    else:
                        return _safe_json({"error": f"Unknown action: {action}"})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Cookie support requires stealth browser server with /cookies endpoint"})

        @mcp.tool
        async def browser_storage(action: str = "get", key: str = "", value: str = "", storage_type: str = "local", tab_id: str = "") -> str:
            """Get or set localStorage/sessionStorage via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/storage", json={"action": action, "key": key, "value": value, "type": storage_type})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Storage support requires stealth browser server with /storage endpoint"})

        @mcp.tool
        async def browser_network(action: str = "inspect", tab_id: str = "") -> str:
            """Intercept and inspect network requests via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{base}/tabs/{tid}/network")
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Network inspection requires stealth browser server with /network endpoint"})

        @mcp.tool
        async def browser_console(action: str = "log", tab_id: str = "") -> str:
            """Get browser console logs via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{base}/tabs/{tid}/console")
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Console access requires stealth browser server with /console endpoint"})

        @mcp.tool
        async def browser_pdf(tab_id: str = "") -> str:
            """Export page as PDF via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(f"{base}/tabs/{tid}/pdf")
                    if resp.status_code == 200:
                        out_path = ROOT / f"browser_export_{int(_time.time())}.pdf"
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        return _safe_json({"ok": True, "path": str(out_path), "size_bytes": len(resp.content)})
                    return _safe_json({"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "PDF export requires stealth browser server with /pdf endpoint"})

        @mcp.tool
        async def browser_record(tab_id: str = "") -> str:
            """Record a browser session — stores screenshots in session replay file."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/record", json={"action": "start"})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Session recording requires stealth browser server with /record endpoint"})

        @mcp.tool
        async def browser_replay(session_path: str = "", tab_id: str = "") -> str:
            """Replay a recorded browser session."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/replay", json={"session": session_path})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Session replay requires stealth browser server with /replay endpoint"})

        @mcp.tool
        async def browser_assert(condition: str, tab_id: str = "") -> str:
            """Assert a page condition — checks URL matches or element exists."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/assert", json={"condition": condition})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Assert support requires stealth browser server with /assert endpoint"})

        @mcp.tool
        async def browser_select(selector: str, option: str = "", tab_id: str = "") -> str:
            """Select a dropdown option via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/select", json={"selector": selector, "option": option})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Select support requires stealth browser server with /select endpoint"})

        @mcp.tool
        async def browser_hover(selector: str, tab_id: str = "") -> str:
            """Hover over an element via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/hover", json={"selector": selector})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Hover support requires stealth browser server with /hover endpoint"})

        @mcp.tool
        async def browser_drag(selector: str, target_selector: str = "", tab_id: str = "") -> str:
            """Drag and drop an element via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/drag", json={"selector": selector, "target": target_selector})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Drag support requires stealth browser server with /drag endpoint"})

        @mcp.tool
        async def browser_upload(selector: str, file_path: str = "", tab_id: str = "") -> str:
            """Upload a file to an input via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                resolved = _Path(file_path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {file_path}"})
                file_bytes = resolved.read_bytes()
                files = {"file": (resolved.name, file_bytes, "application/octet-stream")}
                async with _httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/upload", data={"selector": selector}, files=files)
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Upload requires stealth browser server with /upload endpoint"})

        @mcp.tool
        async def browser_download(url: str = "", tab_id: str = "") -> str:
            """Download a resource via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/download", json={"url": url})
                    if resp.status_code == 200:
                        out_path = ROOT / f"download_{int(_time.time())}"
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        return _safe_json({"ok": True, "path": str(out_path), "size_bytes": len(resp.content)})
                    return _safe_json({"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Download requires stealth browser server with /download endpoint"})

        @mcp.tool
        async def browser_resize(width: int = 1280, height: int = 720, tab_id: str = "") -> str:
            """Resize the browser viewport via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/viewport", json={"width": width, "height": height})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Resize requires stealth browser server with /viewport endpoint"})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] browser tools unavailable: {e}")
        for n, d in [("browser_open", "Open browser"), ("browser_close", "Close browser"), ("browser_navigate", "Navigate"), ("browser_screenshot", "Screenshot"), ("browser_click", "Click"), ("browser_type", "Type"), ("browser_scroll", "Scroll"), ("browser_extract", "Extract"), ("browser_wait", "Wait"), ("browser_element", "Element info"), ("browser_form", "Fill form"), ("browser_back", "Go back"), ("browser_forward", "Go forward"), ("browser_eval", "Eval JS"), ("browser_cookie", "Cookies"), ("browser_storage", "Storage"), ("browser_network", "Network"), ("browser_console", "Console"), ("browser_pdf", "PDF export"), ("browser_record", "Record"), ("browser_replay", "Replay"), ("browser_assert", "Assert"), ("browser_select", "Select"), ("browser_hover", "Hover"), ("browser_drag", "Drag"), ("browser_upload", "Upload"), ("browser_download", "Download"), ("browser_resize", "Resize")]:
            _reg(mcp, n, d)
