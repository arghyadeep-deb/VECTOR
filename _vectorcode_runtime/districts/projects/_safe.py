"""Shared helpers for the projects district."""
import re

_BAD = re.compile(r'[\x00-\x1f/\\:*?"<>|]')


def safe_note_title(raw: str) -> str:
    """Make a caller-supplied project/doc name safe to use as a vault note
    filename: no path separators, no '..' traversal, no control chars.
    ObsidianSync.write_note joins ``folder/title.md`` without resolving, so
    '../../x' would escape the vault."""
    cleaned = _BAD.sub("_", str(raw or "")).replace("..", "_").strip(" ._")
    return cleaned[:120]


if __name__ == "__main__":
    assert "/" not in safe_note_title("../../etc/x") and ".." not in safe_note_title("../../etc/x")
    print("OK _safe.py")
