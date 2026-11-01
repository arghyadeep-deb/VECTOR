"""Compatibility shim — canonical implementation lives in vectorcode.src.vc_tools.scan_chunks."""
from vectorcode.src.vc_tools.scan_chunks import ScanChunksTool  # noqa: F401

__all__ = ["ScanChunksTool", "scan_chunks"]


def scan_chunks(text: str) -> list:
    """Legacy convenience wrapper — delegates to ScanChunksTool."""
    tool = ScanChunksTool()
    result = tool.execute(question=text)
    return [] if not result.success else [result]
