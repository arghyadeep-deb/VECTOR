"""VectorCode display system — spinner, diff preview, renderer."""
from vectorcode.display.spinner import VectorSpinner, get_tool_emoji, get_tool_message

# VectorCode compatibility alias
KawaiiSpinner = VectorSpinner

try:
    from vectorcode.display.diff_preview import build_diff_preview
except ImportError:
    def build_diff_preview(*a, **kw):
        return ""

__all__ = ["VectorSpinner", "KawaiiSpinner", "get_tool_emoji", "get_tool_message", "build_diff_preview"]
