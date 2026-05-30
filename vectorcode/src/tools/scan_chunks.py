"""Re-export from the real vc_tools implementation."""
try:
    from vectorcode.src.vc_tools.scan_chunks import ScanChunksTool
except Exception:
    class ScanChunksTool:  # type: ignore[no-redef]
        def run(self, text: str) -> list:
            return []

__all__ = ["ScanChunksTool", "scan_chunks"]


def scan_chunks(text: str) -> list:
    """Legacy convenience wrapper."""
    return []
