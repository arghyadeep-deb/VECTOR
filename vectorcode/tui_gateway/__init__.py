"""TUI gateway package."""
try:
    from vectorcode.tui_gateway import server
except (ImportError, Exception):
    server = None
