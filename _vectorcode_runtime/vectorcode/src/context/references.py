"""Context references — ported from reference context_references.py.

Parses and expands @mention syntax in user messages:
  @diff               → git diff
  @staged             → git diff --staged
  @file:"path"        → file content (with optional :line-start-end)
  @folder:"path"      → directory listing
  @git:"N"            → git log -N -p
  @url:"url"          → web-fetched HTML stripped to text

Total injected content is capped at 50K characters.
Sensitive paths (SSH keys, .aws, etc.) are blocked.
"""

from __future__ import annotations

import mimetypes
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


try:
    from core.config import CONFIG  # noqa: F401
except ImportError:
    CONFIG = {}

from loguru import logger

# ── Reference pattern ─────────────────────────────────────────────────────────

_QUOTED_REFERENCE_VALUE = r'(?:`[^`\n]+`|"[^"\n]+"|\'[^\'\n]+\')'
REFERENCE_PATTERN = re.compile(
    rf"(?<![\w/])@(?:(?P<simple>diff|staged)\b|"
    rf"(?P<kind>file|folder|git|url):(?P<value>{_QUOTED_REFERENCE_VALUE}"
    rf"(?::\d+(?:-\d+)?)?|\S+))"
)

_TRAILING_PUNCTUATION = ",.;!?"

# ── Sensitive paths (never include) ──────────────────────────────────────────

BLOCKED_PATHS = frozenset({
    ".ssh", ".aws", ".gnupg", ".kube", ".docker",
    ".netrc", ".pgpass", "credentials", ".azure",
    ".config/gh",
})

_SENSITIVE_HOME_FILES = frozenset({
    Path(".ssh") / "authorized_keys",
    Path(".ssh") / "id_rsa",
    Path(".ssh") / "id_ed25519",
    Path(".ssh") / "config",
    Path(".bashrc"),
    Path(".zshrc"),
    Path(".profile"),
    Path(".bash_profile"),
    Path(".zprofile"),
    Path(".netrc"),
    Path(".pgpass"),
    Path(".npmrc"),
    Path(".pypirc"),
})

# Max total injected content
_MAX_INJECTED_CHARS = 50_000


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContextReference:
    """A single @mention parsed from a user message."""

    raw: str          # original @mention text
    kind: str         # "file", "folder", "git", "url", "diff", "staged"
    target: str       # path, URL, or git count
    start: int = 0    # start position in message
    end: int = 0      # end position in message
    line_start: Optional[int] = None
    line_end: Optional[int] = None


@dataclass
class ContextReferenceResult:
    """Result of expanding all @references in a message."""

    message: str           # message with references replaced by their content
    original_message: str
    references: List[ContextReference] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    injected_tokens: int = 0   # estimated tokens injected
    expanded: bool = False
    blocked: bool = False


# ── Parsing ───────────────────────────────────────────────────────────────────


def parse_context_references(message: str) -> List[ContextReference]:
    """Find all @references in a message and return them as ContextReference objects."""
    refs: List[ContextReference] = []
    if not message:
        return refs

    for match in REFERENCE_PATTERN.finditer(message):
        simple = match.group("simple")
        if simple:
            refs.append(
                ContextReference(
                    raw=match.group(0),
                    kind=simple,
                    target="",
                    start=match.start(),
                    end=match.end(),
                )
            )
            continue

        kind = match.group("kind")
        value = _strip_trailing_punctuation(match.group("value") or "")
        line_start: Optional[int] = None
        line_end: Optional[int] = None
        target = _strip_reference_wrappers(value)

        if kind == "file":
            target, line_start, line_end = _parse_file_reference_value(value)

        refs.append(
            ContextReference(
                raw=match.group(0),
                kind=kind,
                target=target,
                start=match.start(),
                end=match.end(),
                line_start=line_start,
                line_end=line_end,
            )
        )

    return refs


# ── Expansion (synchronous) ───────────────────────────────────────────────────


def expand_context_references(
    message: str,
    cwd: Path,
) -> ContextReferenceResult:
    """Replace all @references in message with their content.

    Blocks:
    - paths containing any BLOCKED_PATHS component
    - paths outside cwd (workspace root)

    Caps total injected content at 50K chars.
    """
    refs = parse_context_references(message)
    if not refs:
        return ContextReferenceResult(message=message, original_message=message)

    cwd_path = Path(cwd).expanduser().resolve()
    warnings: List[str] = []
    blocks: List[str] = []
    total_chars = 0

    for ref in refs:
        try:
            warning, block = _expand_reference(ref, cwd_path)
        except Exception as exc:
            warning, block = f"{ref.raw}: {exc}", None

        if warning:
            warnings.append(warning)
        if block:
            if total_chars + len(block) > _MAX_INJECTED_CHARS:
                warnings.append(
                    f"{ref.raw}: skipped — would exceed 50K char injection limit"
                )
                continue
            blocks.append(block)
            total_chars += len(block)

    # Rough token estimate: 1 token ~4 chars
    injected_tokens = total_chars // 4

    stripped = _remove_reference_tokens(message, refs)
    final = stripped
    if warnings:
        final = f"{final}\n\n--- Context Warnings ---\n" + "\n".join(
            f"- {w}" for w in warnings
        )
    if blocks:
        final = f"{final}\n\n--- Attached Context ---\n\n" + "\n\n".join(blocks)

    return ContextReferenceResult(
        message=final.strip(),
        original_message=message,
        references=refs,
        warnings=warnings,
        injected_tokens=injected_tokens,
        expanded=bool(blocks or warnings),
        blocked=False,
    )


# ── Individual reference expanders ───────────────────────────────────────────


def _expand_reference(
    ref: ContextReference, cwd: Path
) -> Tuple[Optional[str], Optional[str]]:
    """Dispatch to the correct expander. Returns (warning, content_block)."""
    if ref.kind == "file":
        return _expand_file_reference(ref, cwd)
    if ref.kind == "folder":
        return _expand_folder_reference(ref, cwd)
    if ref.kind == "diff":
        return _expand_git_cmd(ref, cwd, ["diff"], "git diff")
    if ref.kind == "staged":
        return _expand_git_cmd(ref, cwd, ["diff", "--staged"], "git diff --staged")
    if ref.kind == "git":
        count = max(1, min(int(ref.target or "1"), 10))
        return _expand_git_cmd(ref, cwd, ["log", f"-{count}", "-p"], f"git log -{count} -p")
    if ref.kind == "url":
        content = _fetch_url(ref.target)
        if not content:
            return f"{ref.raw}: no content extracted", None
        return None, f"[url: {ref.raw}]\n{content}"
    return f"{ref.raw}: unsupported reference type", None


def _expand_file_reference(
    ref: ContextReference, cwd: Path
) -> Tuple[Optional[str], Optional[str]]:
    path = _resolve_path(cwd, ref.target)
    _ensure_within_workspace(path, cwd)
    _ensure_path_allowed(path)
    if not path.exists():
        return f"{ref.raw}: file not found", None
    if not path.is_file():
        return f"{ref.raw}: path is not a file", None
    if _is_binary_file(path):
        return f"{ref.raw}: binary files are not supported", None

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return f"{ref.raw}: read error: {exc}", None

    if ref.line_start is not None:
        lines = text.splitlines()
        start_idx = max(ref.line_start - 1, 0)
        end_idx = min(ref.line_end or ref.line_start, len(lines))
        text = "\n".join(lines[start_idx:end_idx])

    lang = _code_fence_language(path)
    return None, f"[file: {ref.raw}]\n```{lang}\n{text}\n```"


def _expand_folder_reference(
    ref: ContextReference, cwd: Path
) -> Tuple[Optional[str], Optional[str]]:
    path = _resolve_path(cwd, ref.target)
    _ensure_within_workspace(path, cwd)
    _ensure_path_allowed(path)
    if not path.exists():
        return f"{ref.raw}: folder not found", None
    if not path.is_dir():
        return f"{ref.raw}: path is not a folder", None

    listing = _build_folder_listing(path, cwd)
    return None, f"[folder: {ref.raw}]\n{listing}"


def _expand_git_cmd(
    ref: ContextReference,
    cwd: Path,
    args: List[str],
    label: str,
) -> Tuple[Optional[str], Optional[str]]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return f"{ref.raw}: git command timed out (30s)", None
    except FileNotFoundError:
        return f"{ref.raw}: git not found", None

    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "git command failed"
        return f"{ref.raw}: {stderr}", None

    content = result.stdout.strip()
    if not content:
        content = "(no output)"
    return None, f"[{label}]\n```diff\n{content}\n```"


def _fetch_url(url: str) -> str:
    """Fetch URL and return stripped text content."""
    try:
        import httpx

        response = httpx.get(url, timeout=15, follow_redirects=True)
        response.raise_for_status()
        text = response.text
        # Strip HTML tags to plain text
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text.strip()[:_MAX_INJECTED_CHARS]
    except ImportError:
        logger.debug("[VECTOR] suppressed exception", exc_info=True)

    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            raw = re.sub(r"<[^>]+>", " ", raw)
            raw = re.sub(r"\s{3,}", "\n\n", raw)
            return raw.strip()[:_MAX_INJECTED_CHARS]
    except Exception as exc:
        logger.debug(f"[VECTOR][references] URL fetch failed for {url}: {exc}")
        return ""


# ── Path helpers ──────────────────────────────────────────────────────────────


def _resolve_path(cwd: Path, target: str) -> Path:
    path = Path(os.path.expanduser(target))
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def _ensure_within_workspace(path: Path, cwd: Path) -> None:
    """Reject resolved paths outside ``cwd``, including Windows case tricks."""
    normalized_path = os.path.normcase(str(path.resolve()))
    normalized_cwd = os.path.normcase(str(cwd.resolve()))
    try:
        inside_workspace = os.path.commonpath((normalized_path, normalized_cwd)) == normalized_cwd
    except ValueError:
        inside_workspace = False
    if not inside_workspace:
        raise ValueError("path resolves outside the workspace and cannot be attached")


def _ensure_path_allowed(path: Path) -> None:
    """Raise ValueError if path is a blocked sensitive file or directory."""
    home = Path.home().resolve()

    # Exact blocked files relative to home
    for rel in _SENSITIVE_HOME_FILES:
        if path == (home / rel).resolve():
            raise ValueError("path is a sensitive credential file and cannot be attached")

    # Blocked directory prefixes
    for blocked_dir_name in BLOCKED_PATHS:
        # Check both as a relative-to-home dir and as any path component
        blocked_abs = home / blocked_dir_name
        try:
            path.relative_to(blocked_abs.resolve())
            raise ValueError(
                "path is inside a sensitive directory and cannot be attached"
            )
        except ValueError as exc:
            if "sensitive" in str(exc):
                raise
        # Also check if the component appears anywhere in the path parts
        for part in path.parts:
            if part.lower() == blocked_dir_name.lower():
                raise ValueError(
                    f"path contains sensitive component '{part}' and cannot be attached"
                )


def _strip_trailing_punctuation(value: str) -> str:
    stripped = value.rstrip(_TRAILING_PUNCTUATION)
    while stripped.endswith((")", "]", "}")):
        closer = stripped[-1]
        opener = {")": "(", "]": "[", "}": "{"}[closer]
        if stripped.count(closer) > stripped.count(opener):
            stripped = stripped[:-1]
            continue
        break
    return stripped


def _strip_reference_wrappers(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "`\"'":
        return value[1:-1]
    return value


def _parse_file_reference_value(
    value: str,
) -> Tuple[str, Optional[int], Optional[int]]:
    """Parse file path with optional line range: "path":10-20 or "path":10."""
    quoted_match = re.match(
        r'^(?P<quote>`|"|\')(?P<path>.+?)(?P=quote)'
        r'(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?$',
        value,
    )
    if quoted_match:
        line_start_str = quoted_match.group("start")
        line_end_str = quoted_match.group("end")
        return (
            quoted_match.group("path"),
            int(line_start_str) if line_start_str is not None else None,
            int(line_end_str or line_start_str) if line_start_str is not None else None,
        )

    range_match = re.match(r"^(?P<path>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$", value)
    if range_match:
        line_start = int(range_match.group("start"))
        return (
            range_match.group("path"),
            line_start,
            int(range_match.group("end") or range_match.group("start")),
        )

    return _strip_reference_wrappers(value), None, None


def _remove_reference_tokens(message: str, refs: List[ContextReference]) -> str:
    """Remove all @reference tokens from message, cleaning up extra whitespace."""
    pieces: List[str] = []
    cursor = 0
    for ref in refs:
        pieces.append(message[cursor : ref.start])
        cursor = ref.end
    pieces.append(message[cursor:])
    text = "".join(pieces)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def _is_binary_file(path: Path) -> bool:
    mime, _ = mimetypes.guess_type(path.name)
    if mime and not mime.startswith("text/") and not any(
        path.name.endswith(ext)
        for ext in (
            ".py", ".md", ".txt", ".json", ".yaml", ".yml",
            ".toml", ".js", ".ts", ".tsx", ".jsx",
        )
    ):
        return True
    try:
        chunk = path.read_bytes()[:4096]
        return b"\x00" in chunk
    except Exception:
        return False


def _build_folder_listing(path: Path, cwd: Path, limit: int = 200) -> str:
    """Build a simple text listing of a directory."""
    try:
        rel_root = path.relative_to(cwd)
    except ValueError:
        rel_root = path
    lines = [f"{rel_root}/"]
    count = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        root_path = Path(root)
        try:
            rel = root_path.relative_to(cwd)
        except ValueError:
            rel = root_path
        indent = "  " * max(len(rel.parts) - len(rel_root.parts), 0)
        for d in sorted(dirs):
            lines.append(f"{indent}- {d}/")
            count += 1
            if count >= limit:
                lines.append("- ...")
                return "\n".join(lines)
        for f in sorted(files):
            lines.append(f"{indent}- {f}")
            count += 1
            if count >= limit:
                lines.append("- ...")
                return "\n".join(lines)
    return "\n".join(lines)


def _code_fence_language(path: Path) -> str:
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".jsx": "jsx",
        ".json": "json",
        ".md": "markdown",
        ".sh": "bash",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
    }
    return mapping.get(path.suffix.lower(), "")


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    # parse_context_references — @diff and @staged
    refs = parse_context_references("show me @diff and @staged please")
    assert len(refs) == 2
    assert refs[0].kind == "diff"
    assert refs[1].kind == "staged"

    # parse_context_references — @file with quotes
    refs2 = parse_context_references('check @file:"README.md" for issues')
    assert len(refs2) == 1
    assert refs2[0].kind == "file"
    assert refs2[0].target == "README.md"

    # parse_context_references — @file with line range
    refs3 = parse_context_references('@file:"src/main.py":10-20')
    assert len(refs3) == 1
    assert refs3[0].line_start == 10
    assert refs3[0].line_end == 20

    # parse_context_references — @url
    refs4 = parse_context_references('@url:"https://example.com"')
    assert len(refs4) == 1
    assert refs4[0].kind == "url"
    assert refs4[0].target == "https://example.com"

    # parse_context_references — @git
    refs5 = parse_context_references('@git:"3"')
    assert len(refs5) == 1
    assert refs5[0].kind == "git"
    assert refs5[0].target == "3"

    # empty message
    refs6 = parse_context_references("")
    assert refs6 == []

    # expand_context_references with a real file
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        test_file = tmp_path / "test.py"
        test_file.write_text("# hello\nprint('world')\n", encoding="utf-8")

        result = expand_context_references(
            f'check @file:"{test_file}" for bugs',
            cwd=tmp_path,
        )
        assert result.expanded is True
        assert "hello" in result.message or "world" in result.message
        assert result.injected_tokens > 0

        # line range
        result2 = expand_context_references(
            f'@file:"{test_file}":1-1',
            cwd=tmp_path,
        )
        assert result2.expanded is True

        # missing file
        result3 = expand_context_references(
            '@file:"nonexistent.py"',
            cwd=tmp_path,
        )
        assert len(result3.warnings) > 0

        # @folder
        result4 = expand_context_references(
            f'@folder:"{tmp_path}"',
            cwd=tmp_path,
        )
        assert result4.expanded is True
        assert "test.py" in result4.message

    # blocked path check
    home = Path.home()
    try:
        _ensure_path_allowed((home / ".ssh" / "id_rsa").resolve())
        assert False, "should have raised ValueError"
    except ValueError as _sve:
        logger.debug("[VECTOR][context.references] suppressed ValueError: %s", _sve)

    print("context/references.py OK")

