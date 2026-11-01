"""
Module: core/brain/blueprint_doctrine.py
Loads the owner's operating doctrine from the Brain vault (Blueprint/(C) Doctrine.md)
and exposes the Hydration Line for injection into session_hydration_prompt().

Claude-independent by design: the doctrine lives in the Obsidian Brain, not in
.claude/ config, so it survives any change of build tooling or LLM provider.
Degrades to "" on any failure — the loop must never die because a vault file moved.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

from core.config import CONFIG

DOCTRINE_RELPATH = Path("Blueprint") / "(C) Doctrine.md"
HYDRATION_HEADER = "## Hydration Line"
_MAX_LINE_CHARS = 600  # hard cap — this text rides on every LLM call

_cache: dict = {"path": None, "mtime": None, "line": ""}


def _vault_candidates() -> list[Path]:
    """Brain vault locations, most authoritative first."""
    candidates: list[Path] = []
    try:
        candidates.append(Path(CONFIG["knowledge"]["wiki_root"]))
    except Exception:
        pass
    try:
        candidates.append(Path(CONFIG["obsidian"]["vault_path"]))
    except Exception:
        pass
    return candidates


def _doctrine_path() -> Path | None:
    for vault in _vault_candidates():
        p = vault / DOCTRINE_RELPATH
        if p.is_file():
            return p
    return None


def _extract_hydration_line(text: str) -> str:
    """Return the body of the '## Hydration Line' section, whitespace-joined."""
    lines: list[str] = []
    in_section = False
    for raw in text.splitlines():
        if raw.strip().startswith("## "):
            if in_section:
                break
            in_section = raw.strip() == HYDRATION_HEADER
            continue
        if in_section and raw.strip() and not raw.strip().startswith(">"):
            lines.append(raw.strip())
    return " ".join(lines)[:_MAX_LINE_CHARS]


VALID_REGIMES = ("NORMAL", "CORRECTION", "CRISIS")


def get_regime() -> str:
    """Current market regime from the Doctrine wave-state table ('| Regime | X |').
    Owner-declared (RED-tier decision); defaults to NORMAL if unreadable — agents must
    never freeze because the vault is unavailable."""
    try:
        path = _doctrine_path()
        if path is None:
            return "NORMAL"
        for raw in path.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in raw.split("|")]
            if len(cells) >= 3 and cells[1].lower() == "regime":
                value = cells[2].split("—")[0].split("(")[0].strip().upper()
                if value in VALID_REGIMES:
                    return value
                logger.warning(f"[VECTOR][doctrine] unknown regime '{value}', defaulting NORMAL")
                return "NORMAL"
        return "NORMAL"
    except Exception as e:
        logger.warning(f"[VECTOR][doctrine] regime read failed, defaulting NORMAL: {e}")
        return "NORMAL"


def get_doctrine_line() -> str:
    """Hydration Line from the Brain's Blueprint doctrine, or "" if unavailable.
    Cached by file mtime so the vault is only re-read when the owner edits it."""
    try:
        path = _doctrine_path()
        if path is None:
            return ""
        mtime = path.stat().st_mtime
        if _cache["path"] == path and _cache["mtime"] == mtime:
            return _cache["line"]
        line = _extract_hydration_line(path.read_text(encoding="utf-8"))
        _cache.update(path=path, mtime=mtime, line=line)
        if line:
            logger.info(f"[VECTOR][doctrine] loaded hydration line from {path.name}")
        return line
    except Exception as e:
        logger.warning(f"[VECTOR][doctrine] load failed, continuing without doctrine: {e}")
        return ""


if __name__ == "__main__":
    # real test, no mocks
    result = get_doctrine_line()
    regime = get_regime()
    print(f"doctrine: {result[:120]}...")
    print(f"regime: {regime}")
    ok = result.startswith("DOCTRINE:") and regime in VALID_REGIMES
    print("✅ blueprint_doctrine OK" if ok else "❌ FAILED")
