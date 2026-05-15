"""VECTOR display utilities."""
try:
    from vectorcode.src.display.diff_preview import build_diff_preview
except ImportError:
    def build_diff_preview(old: str, new: str, context: int = 3) -> str:
        import difflib
        return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), n=context))
