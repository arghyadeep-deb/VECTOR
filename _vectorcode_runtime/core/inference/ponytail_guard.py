"""
core/inference/ponytail_guard.py — inject the ponytail minimal-code ladder into every
coding/SaaS LLM call VECTOR makes, so agents build lean instead of us auditing bloat later.

Wired in vectorcode_llm.chat(): one injection point, all ~25 coding agents covered
(ponytail's own rung 2 — don't wire it 25 times). The ladder text is loaded from the
vendored plugin at ponytail/skills/ponytail/SKILL.md — edit that file to change behavior;
no code change needed. mtime-cached; degrades to "" if the plugin is missing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

_LADDER_PATH = Path(__file__).parent.parent.parent / "ponytail" / "skills" / "ponytail" / "SKILL.md"

# Domains where minimal-code discipline applies. Coding + SaaS product build; NOT
# content/research/summarization (prose) or security (its own local-only gate).
_CODING_PREFIXES = ("coding.", "saas.")

# Compact system injection — the ladder distilled to the load-bearing rungs. Full text
# lives in the SKILL.md; this is what rides every call, so it stays short (token cost).
_INJECTION = (
    "PONYTAIL (minimal-code, ACTIVE): You are a lazy senior dev — laziest solution that "
    "works. Ladder, stop at first rung that holds: (1) does this need to exist? skip if "
    "speculative (YAGNI); (2) already in this codebase? reuse it — re-implementing what's a "
    "few files over is the most common slop; (3) stdlib does it? use it; (4) platform-native? "
    "use it; (5) installed dep solves it? use it, never add one for a few lines; (6) one line? "
    "one line; (7) only then minimal code that works. No interface with one impl, no factory "
    "for one product, no config nobody sets, no scaffolding 'for later'. Deletion over "
    "addition. Bug fix = root cause in the shared function, not a guard per caller."
)

_cache: dict = {"mtime": None, "ok": None}


def _plugin_present() -> bool:
    """True if the vendored ponytail ladder file exists (mtime-cached)."""
    try:
        mtime = _LADDER_PATH.stat().st_mtime
        if _cache["mtime"] != mtime:
            _cache.update(mtime=mtime, ok=True)
            logger.info("[VECTOR][ponytail] minimal-code guard active (plugin found)")
        return True
    except OSError:
        if _cache["ok"] is not False:
            _cache.update(mtime=None, ok=False)
            logger.warning("[VECTOR][ponytail] plugin not at ponytail/ — minimal-code guard off")
        return False


def applies_to(domain: str, model: str = "") -> bool:
    """Does the ladder apply to this call's domain?"""
    d = (domain or model or "").lower()
    return d.startswith(_CODING_PREFIXES)


def inject(messages: list[dict], domain: str = "", model: str = "") -> list[dict]:
    """Return messages with the ponytail ladder prepended to the system prompt for
    coding/SaaS calls. No-op otherwise, or if the plugin is absent. Never raises."""
    try:
        if not applies_to(domain, model) or not _plugin_present():
            return messages
        for m in messages:
            if m.get("role") == "system":
                if "PONYTAIL" not in m.get("content", ""):
                    m["content"] = _INJECTION + "\n\n" + m.get("content", "")
                return messages
        return [{"role": "system", "content": _INJECTION}, *messages]
    except Exception as e:
        logger.debug(f"[VECTOR][ponytail] inject skipped: {e}")
        return messages


if __name__ == "__main__":
    # real test, no mocks
    out = inject([{"role": "system", "content": "You review code."}], domain="coding.review")
    ok = "PONYTAIL" in out[0]["content"] and inject([{"role": "user", "content": "hi"}], domain="content.script") == [{"role": "user", "content": "hi"}]
    print("ponytail_guard OK" if ok else "FAILED")
