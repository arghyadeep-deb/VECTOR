"""Color theme engine — ANSI color schemes for VectorCode terminal output."""
import re
import os
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


from loguru import logger


@dataclass
class ColorTheme:
    name: str
    # Primary colors
    primary: str = "\x1b[36m"             # cyan
    secondary: str = "\x1b[96m"           # bright cyan
    accent: str = "\x1b[94m"              # bright blue
    # Status colors
    success: str = "\x1b[92m"             # bright green
    warning: str = "\x1b[93m"             # bright yellow
    error: str = "\x1b[91m"               # bright red
    info: str = "\x1b[2m\x1b[37m"         # dim white
    # Text styles
    bold: str = "\x1b[1m"
    dim: str = "\x1b[2m"
    reset: str = "\x1b[0m"
    # Tool-specific
    tool_name: str = "\x1b[35m"           # magenta
    file_path: str = "\x1b[33m"           # yellow
    code_block: str = "\x1b[2m\x1b[32m"  # dim green
    # No-color mode
    no_color: bool = False


# Built-in themes
THEMES: dict[str, ColorTheme] = {
    "default": ColorTheme(name="default"),
    "dark": ColorTheme(
        name="dark",
        primary="\x1b[34m",
        secondary="\x1b[94m",
        accent="\x1b[35m",
    ),
    "light": ColorTheme(
        name="light",
        primary="\x1b[34m",
        secondary="\x1b[32m",
        accent="\x1b[35m",
        dim="\x1b[2m",
    ),
    "minimal": ColorTheme(
        name="minimal",
        primary="", secondary="", accent="",
        success="", warning="", error="",
        info="", bold="", dim="", reset="",
        tool_name="", file_path="", code_block="",
        no_color=True,
    ),
    "vector": ColorTheme(
        name="vector",
        primary="\x1b[36m",    # VECTOR cyan
        secondary="\x1b[96m",
        accent="\x1b[94m",
        success="\x1b[92m",
        warning="\x1b[93m",
        error="\x1b[91m",
        tool_name="\x1b[35m",
        file_path="\x1b[33m",
    ),
}


def _parse_toml_theme(text: str) -> dict:
    """
    Minimal TOML key=value parser for theme files.
    Handles:  key = "value"  and  key = true/false
    Escape sequences like \\x1b are converted to actual bytes.
    Falls back to tomllib on Python 3.11+ when available.
    """
    try:
        import tomllib  # Python 3.11+
        raw = tomllib.loads(text)
        # tomllib won't unescape \\x1b — handle manually
        result: dict = {}
        for k, v in raw.items():
            if isinstance(v, str):
                # Convert Python-style escape literals written as \\x1b inside TOML strings
                try:
                    result[k] = bytes(v, "utf-8").decode("unicode_escape")
                except Exception:
                    result[k] = v
            else:
                result[k] = v
        return result
    except Exception as _sve:
        logger.debug("[VECTOR][config.theme] suppressed Exception: {}", _sve)

    # Regex-based fallback
    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^(\w+)\s*=\s*"(.*)"$', line)
        if m:
            key = m.group(1)
            val = m.group(2)
            # Unescape \\x1b → actual ESC, \\x1b[... sequences
            try:
                val = bytes(val, "utf-8").decode("unicode_escape")
            except Exception as _sve:
                logger.debug("[VECTOR][config.theme] suppressed Exception: {}", _sve)
            result[key] = val
            continue
        m = re.match(r'^(\w+)\s*=\s*(true|false)$', line)
        if m:
            result[m.group(1)] = m.group(2) == "true"
    return result


_THEME_FIELDS = {f.name for f in ColorTheme.__dataclass_fields__.values()}  # type: ignore[attr-defined]


class ThemeEngine:
    """
    Manages the active color theme.  Respects NO_COLOR env var.
    Loads custom themes from ~/.vector/themes/ directory.
    """

    def __init__(self) -> None:
        self._active_name: str = "vector"
        self._themes: dict[str, ColorTheme] = dict(THEMES)
        self._no_color: bool = bool(os.environ.get("NO_COLOR", ""))
        self._load_custom_themes()

    # ── public API ────────────────────────────────────────────────────────────

    def use(self, name: str) -> "ColorTheme":
        """Switch to named theme.  Returns the theme."""
        if name not in self._themes:
            logger.warning(f"[VECTOR][theme] unknown theme '{name}' — keeping '{self._active_name}'")
            return self.current()
        self._active_name = name
        logger.debug(f"[VECTOR][theme] switched to '{name}'")
        return self._themes[name]

    def current(self) -> ColorTheme:
        """Return the active theme."""
        return self._themes.get(self._active_name, THEMES["vector"])

    def list_themes(self) -> list[str]:
        """Return list of available theme names."""
        return sorted(self._themes.keys())

    def add_theme(self, theme: ColorTheme) -> None:
        """Register a custom theme."""
        self._themes[theme.name] = theme
        logger.debug(f"[VECTOR][theme] registered custom theme '{theme.name}'")

    def colorize(self, text: str, style: str) -> str:
        """
        Apply a named style from the current theme to text.
        style: "primary" | "secondary" | "success" | "error" | "warning" |
               "info" | "bold" | "dim" | "tool_name" | "file_path" | "code_block"
        Returns text wrapped in ANSI codes, or plain text when no_color active.
        """
        theme = self.current()
        if theme.no_color or self._no_color:
            return text
        code = getattr(theme, style, "")
        if not code:
            return text
        return f"{code}{text}{theme.reset}"

    def strip_ansi(self, text: str) -> str:
        """Remove all ANSI escape codes from text."""
        return re.sub(r'\x1b\[[0-9;]*m', '', text)

    def save_theme(self, theme: ColorTheme) -> None:
        """Save a custom theme to ~/.vector/themes/{name}.toml."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+", theme.name):
            raise ValueError(
                "Theme name may contain only letters, numbers, underscores, and hyphens"
            )
        themes_dir = Path.home() / ".vector" / "themes"
        themes_dir.mkdir(parents=True, exist_ok=True)
        out_path = themes_dir / f"{theme.name}.toml"
        lines = [f"name = {json.dumps(theme.name)}"]
        for fname in _THEME_FIELDS:
            if fname == "name":
                continue
            val = getattr(theme, fname)
            if isinstance(val, bool):
                lines.append(f'{fname} = {"true" if val else "false"}')
            else:
                # Store escape codes as Python literals so they survive round-trip
                escaped = val.encode("unicode_escape").decode("ascii")
                lines.append(f"{fname} = {json.dumps(escaped)}")
        fd, tmp_path = tempfile.mkstemp(
            dir=str(themes_dir), prefix=f".{theme.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, out_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.info(f"[VECTOR][theme] saved theme '{theme.name}' → {out_path}")

    # ── private ───────────────────────────────────────────────────────────────

    def _load_custom_themes(self) -> None:
        """
        Load TOML theme files from ~/.vector/themes/*.toml.
        Each file defines a ColorTheme by name.
        Silently ignores missing / malformed files.
        """
        themes_dir = Path.home() / ".vector" / "themes"
        if not themes_dir.exists():
            return
        for toml_file in themes_dir.glob("*.toml"):
            try:
                text = toml_file.read_text(encoding="utf-8")
                data = _parse_toml_theme(text)
                if "name" not in data:
                    data["name"] = toml_file.stem
                # Only pass known fields to the dataclass
                known = {k: v for k, v in data.items() if k in _THEME_FIELDS}
                theme = ColorTheme(**known)
                self._themes[theme.name] = theme
                logger.debug(f"[VECTOR][theme] loaded custom theme '{theme.name}' from {toml_file.name}")
            except Exception as exc:
                logger.warning(f"[VECTOR][theme] failed to load {toml_file.name}: {exc}")


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional["ThemeEngine"] = None


def get_theme_engine() -> ThemeEngine:
    """Singleton accessor."""
    global _engine
    if _engine is None:
        _engine = ThemeEngine()
    return _engine


# ── Convenience functions ─────────────────────────────────────────────────────

def colorize(text: str, style: str) -> str:
    """Colorize text using the active theme."""
    return get_theme_engine().colorize(text, style)


def c_primary(text: str) -> str:   return colorize(text, "primary")
def c_secondary(text: str) -> str: return colorize(text, "secondary")
def c_success(text: str) -> str:   return colorize(text, "success")
def c_warning(text: str) -> str:   return colorize(text, "warning")
def c_error(text: str) -> str:     return colorize(text, "error")
def c_info(text: str) -> str:      return colorize(text, "info")
def c_bold(text: str) -> str:      return colorize(text, "bold")
def c_dim(text: str) -> str:       return colorize(text, "dim")
def c_tool(text: str) -> str:      return colorize(text, "tool_name")
def c_file(text: str) -> str:      return colorize(text, "file_path")
def c_code(text: str) -> str:      return colorize(text, "code_block")


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = get_theme_engine()

    # list_themes returns >= 5 built-in themes
    themes = engine.list_themes()
    assert len(themes) >= 5, f"Expected >= 5 themes, got {themes}"

    # use("dark") switches correctly
    dark = engine.use("dark")
    assert dark.name == "dark", f"Expected 'dark', got {dark.name}"
    assert engine.current().name == "dark"

    # colorize wraps text in ANSI when color is active
    result = engine.colorize("hello", "primary")
    assert len(result) > len("hello"), f"colorize should wrap text, got: {repr(result)}"
    assert "\x1b[" in result, f"Expected ANSI in result: {repr(result)}"

    # use("minimal") → no-color mode returns plain text
    engine.use("minimal")
    plain = engine.colorize("hello", "primary")
    assert plain == "hello", f"minimal theme should return plain text, got: {repr(plain)}"

    # back to vector
    engine.use("vector")
    assert engine.current().name == "vector"

    # strip_ansi removes codes
    stripped = engine.strip_ansi("\x1b[36mhello\x1b[0m")
    assert stripped == "hello", f"strip_ansi failed: {repr(stripped)}"

    # convenience shorthand functions
    assert c_primary("x") != "x" or os.environ.get("NO_COLOR")

    # unknown theme gracefully falls back
    engine.use("nonexistent_xyz")
    assert engine.current().name == "vector"  # unchanged

    # add_theme registers correctly
    custom = ColorTheme(name="test_custom", primary="\x1b[31m")
    engine.add_theme(custom)
    assert "test_custom" in engine.list_themes()

    print("config/theme.py OK")
