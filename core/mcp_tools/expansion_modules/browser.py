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

        def _ssrf_reason(url: str) -> str | None:
            """None when ``url`` is safe to hand to the browser, else the block reason."""
            from core.security.ssrf_guard import SSRFGuard

            if (url or "").startswith("@"):
                return None  # server-side search macro (@google_search:query), not a URL
            check = SSRFGuard(resolve_dns=True).check_url(url)
            if check.safe:
                return None
            logger.warning("[VECTOR][mcp] browser URL blocked by SSRF guard: {}", check.reason)
            return check.reason

        @mcp.tool
        async def browser_open() -> str:
            """Open a new browser session."""
            try:
                tab = await _get_browser().create_tab()
                return _safe_json({"ok": True, "tab_id": tab.get("tabId") if isinstance(tab, dict) else tab, "tab": tab})
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_open failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_close(tab_id: str = "") -> str:
            """Close browser session or specific tab."""
            try:
                client = _get_browser()
                if tab_id:
                    await client.close_tab(tab_id)
                else:
                    await client.close_all_tabs()
                return _safe_json({"ok": True})
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_close failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_navigate(url: str, tab_id: str = "") -> str:
            """Navigate to a URL."""
            blocked = _ssrf_reason(url)
            if blocked:
                return _safe_json({"error": f"URL blocked by SSRF guard: {blocked}"})
            try:
                result = await _get_browser().navigate(tab_id or "default", url)
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_navigate failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_screenshot(tab_id: str = "") -> str:
            """Take a screenshot of current page."""
            try:
                png = await _get_browser().screenshot(tab_id or "default")
                if not png:
                    return _safe_json({"error": "empty screenshot returned by browser server"})
                import base64 as _b64
                return _safe_json({"ok": True, "format": "png", "size_bytes": len(png), "base64": _b64.b64encode(png).decode("ascii")})
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_screenshot failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_click(selector: str, tab_id: str = "") -> str:
            """Click an element by selector."""
            try:
                import re as _re
                client = _get_browser()
                if _re.fullmatch(r"e\d+", selector or ""):
                    result = await client.click(tab_id or "default", ref=selector)
                else:
                    result = await client.click(tab_id or "default", selector=selector)
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_click failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_type(text: str, selector: str = "", tab_id: str = "") -> str:
            """Type text into an input element."""
            try:
                result = await _get_browser().type_text(tab_id or "default", text, ref=selector or None)
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_type failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_scroll(direction: str = "down", amount: int = 500, tab_id: str = "") -> str:
            """Scroll the page."""
            try:
                result = await _get_browser().scroll(tab_id or "default", direction, amount)
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_scroll failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_extract(tab_id: str = "") -> str:
            """Extract text content from page."""
            try:
                result = await _get_browser().snapshot(tab_id or "default")
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_extract failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_wait(selector: str = "", ms: int = 1000, tab_id: str = "") -> str:
            """Wait for an element or time."""
            try:
                result = await _get_browser().wait(tab_id or "default", selector, ms)
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_wait failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_element(selector: str, tab_id: str = "") -> str:
            """Get info about a page element."""
            try:
                snapshot = await _get_browser().snapshot(tab_id or "default")
                return _safe_json({"selector": selector, "snapshot": snapshot})
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_element failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_form(selector: str, values: str = "{}", tab_id: str = "") -> str:
            """Fill a form with JSON values."""
            try:
                client = _get_browser()
                vals = _json.loads(values) if values else {}
                results = []
                for field, value in vals.items():
                    await client.type_text(tab_id or "default", str(value), ref=f"{selector} [name={field}]")
                    results.append({"field": field, "value": value})
                return _safe_json({"ok": True, "filled": results})
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_form failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_back(tab_id: str = "") -> str:
            """Navigate back in history."""
            try:
                result = await _get_browser().go_back(tab_id or "default")
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_back failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_forward(tab_id: str = "") -> str:
            """Navigate forward in history."""
            try:
                result = await _get_browser().go_forward(tab_id or "default")
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] browser_forward failed: {}", e)
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
            blocked = _ssrf_reason(url)
            if blocked:
                return _safe_json({"error": f"URL blocked by SSRF guard: {blocked}"})
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
