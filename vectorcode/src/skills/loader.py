"""Skill loading and preprocessing -- ported from reference skill_utils.py + skill_preprocessing.py.

Discovers SKILL.md files from three directories (in order):
  1. vectorcode/skills/     (absorbed reference skills)
  2. ~/.claude/skills/      (Claude Code installed skills)
  3. ~/.vector/skills/      (user custom skills)

Applies template substitution (${VECTOR_SKILL_DIR}, ${VECTOR_SESSION_ID}) and
optional inline shell expansion (!`cmd`) on load.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


try:
    from core.config import CONFIG  # noqa: F401
except ImportError:
    CONFIG = {}

from loguru import logger

# ── Lazy YAML loader ──────────────────────────────────────────────────────────

_yaml_load_fn = None

def _yaml_load(content: str) -> Any:
    """Parse YAML with lazy import; prefers CSafeLoader for speed."""
    global _yaml_load_fn
    if _yaml_load_fn is None:
        try:
            import yaml

            loader = getattr(yaml, "CSafeLoader", None) or yaml.SafeLoader

            def _load(value: str) -> Any:
                return yaml.load(value, Loader=loader)

            _yaml_load_fn = _load
        except ImportError:
            _yaml_load_fn = None
    if _yaml_load_fn is not None:
        return _yaml_load_fn(content)
    return None  # fallback triggers simple parser below

# ── Platform mapping ──────────────────────────────────────────────────────────

_PLATFORM_MAP = {
    "macos": "darwin",
    "linux": "linux",
    "windows": "win32",
}

_EXCLUDED_SKILL_DIRS = frozenset((".git", ".github", ".hub"))

# ── Template + inline-shell patterns ─────────────────────────────────────────

_SKILL_TEMPLATE_RE = re.compile(r"\$\{(VECTOR_SKILL_DIR|VECTOR_SESSION_ID)\}")
_INLINE_SHELL_RE = re.compile(r"!`([^`\n]+)`")
_INLINE_SHELL_MAX_OUTPUT = 4000

# ── Frontmatter parsing ───────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter between --- delimiters. Returns (metadata, body).

    Tries PyYAML CSafeLoader first; falls back to simple key:value splitting
    for robustness with malformed frontmatter.
    """
    frontmatter: Dict[str, Any] = {}
    body = content

    if not content.startswith("---"):
        return frontmatter, body

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return frontmatter, body

    yaml_content = content[3 : end_match.start() + 3]
    body = content[end_match.end() + 3 :]

    try:
        parsed = _yaml_load(yaml_content)
        if isinstance(parsed, dict):
            frontmatter = parsed
            return frontmatter, body
    except Exception as _sve:
        logger.debug("[VECTOR][skills.loader] suppressed Exception: {}", _sve)

    # Fallback: simple key:value for malformed YAML
    for line in yaml_content.strip().split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()

    return frontmatter, body

# ── Platform matching ─────────────────────────────────────────────────────────

def skill_matches_platform(frontmatter: Dict[str, Any]) -> bool:
    """Return True when the skill is compatible with the current OS.

    Skills declare platform requirements via a ``platforms`` list:
        platforms: [macos]          # macOS only
        platforms: [macos, windows] # macOS and Windows

    Absent or empty = compatible with ALL platforms.
    """
    platforms = frontmatter.get("platforms")
    if not platforms:
        return True
    if not isinstance(platforms, list):
        platforms = [platforms]
    current = sys.platform
    for platform in platforms:
        normalized = str(platform).lower().strip()
        mapped = _PLATFORM_MAP.get(normalized, normalized)
        if current.startswith(mapped):
            return True
    return False

# ── Skill directory discovery ─────────────────────────────────────────────────

def get_all_skills_dirs() -> List[Path]:
    """Return all skill directories to search, in priority order.

    1. vectorcode/skills/  (reference absorbed skills shipped with VectorCode)
    2. ~/.claude/skills/   (Claude Code installed skills)
    3. ~/.vector/skills/   (user custom skills)
    """
    dirs: List[Path] = []

    # 1. vectorcode package skills dir (sibling of this file's parent)
    pkg_root = Path(__file__).parent.parent  # vectorcode/
    vc_skills = pkg_root / "skills"
    if vc_skills.is_dir():
        dirs.append(vc_skills)

    # 2. ~/.claude/skills/
    claude_skills = Path.home() / ".claude" / "skills"
    if claude_skills.is_dir() and claude_skills not in dirs:
        dirs.append(claude_skills)

    # 3. ~/.vector/skills/
    try:
        from vector_constants import get_vector_skills_dir

        vector_skills = get_vector_skills_dir()
    except Exception:
        vector_skills = Path.home() / ".vector" / "skills"
    if vector_skills.is_dir() and vector_skills not in dirs:
        dirs.append(vector_skills)

    return dirs

def _iter_skill_index_files(skills_dir: Path, filename: str = "SKILL.md"):
    """Walk skills_dir yielding sorted paths matching filename."""
    matches: List[Path] = []
    for root, dirs, files in os.walk(skills_dir, followlinks=True):
        dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED_SKILL_DIRS)
        if filename in files:
            matches.append(Path(root) / filename)
    for path in sorted(matches, key=lambda p: str(p.relative_to(skills_dir))):
        yield path

def list_all_skills() -> Dict[str, Path]:
    """Return {slug: SKILL.md path} for every discoverable skill.

    Slug = directory name, lowercased with hyphens normalized.
    Skills discovered earlier (higher-priority directories) win on name collision.
    """
    result: Dict[str, Path] = {}
    for skills_dir in get_all_skills_dirs():
        if not skills_dir.is_dir():
            continue
        for skill_file in _iter_skill_index_files(skills_dir):
            slug = skill_file.parent.name.lower().replace("_", "-")
            if slug not in result:
                result[slug] = skill_file
    return result

# ── Template substitution ─────────────────────────────────────────────────────

def substitute_template_vars(
    content: str,
    skill_dir: Optional[Path],
    session_id: Optional[str],
) -> str:
    """Replace ${VECTOR_SKILL_DIR} and ${VECTOR_SESSION_ID} in content.

    Unresolved tokens (no value available) are left in place.
    """
    if not content:
        return content
    skill_dir_str = str(skill_dir) if skill_dir else None

    def _replace(match: re.Match) -> str:
        token = match.group(1)
        if token == "VECTOR_SKILL_DIR" and skill_dir_str:
            return skill_dir_str
        if token == "VECTOR_SESSION_ID" and session_id:
            return str(session_id)
        return match.group(0)

    return _SKILL_TEMPLATE_RE.sub(_replace, content)

# ── Inline shell expansion ────────────────────────────────────────────────────

def _run_inline_shell(command: str, cwd: Optional[Path], timeout: int) -> str:
    """Execute a shell snippet and return its stdout (trimmed)."""
    try:
        completed = subprocess.run(
            ["bash", "-c", command],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"[inline-shell timeout after {timeout}s: {command}]"
    except FileNotFoundError:
        # bash not found (Windows without WSL)
        try:
            completed = subprocess.run(
                ["cmd", "/c", command],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=max(1, int(timeout)),
                check=False,
            )
        except Exception as exc:
            return f"[inline-shell error: {exc}]"
    except Exception as exc:
        return f"[inline-shell error: {exc}]"

    output = (completed.stdout or "").rstrip("\n")
    if not output and completed.stderr:
        output = completed.stderr.rstrip("\n")
    if len(output) > _INLINE_SHELL_MAX_OUTPUT:
        output = output[:_INLINE_SHELL_MAX_OUTPUT] + "...[truncated]"
    return output

def expand_inline_shell(
    content: str,
    skill_dir: Optional[Path],
    timeout: int = 10,
) -> str:
    """Replace every !`cmd` snippet in content with its stdout output."""
    if "!`" not in content:
        return content

    def _replace(match: re.Match) -> str:
        cmd = match.group(1).strip()
        if not cmd:
            return ""
        return _run_inline_shell(cmd, skill_dir, timeout)

    return _INLINE_SHELL_RE.sub(_replace, content)

# ── Skill loading ─────────────────────────────────────────────────────────────

def load_skill(name_or_path: str, session_id: str = "") -> Dict[str, Any]:
    """Load a skill by name or file path.

    Returns:
        {
          "name": str,
          "description": str,
          "body": str,
          "frontmatter": dict,
          "path": Path,
          "capabilities": list[str],
        }

    Raises:
        FileNotFoundError: if the skill cannot be found.
        ValueError: if the skill is not compatible with the current platform.
    """
    # Try as direct path first
    maybe_path = Path(name_or_path)
    if maybe_path.is_file():
        skill_path = maybe_path
    else:
        # Search by slug
        slug = name_or_path.lower().replace("_", "-")
        all_skills = list_all_skills()
        if slug not in all_skills:
            # Try prefix match
            candidates = [k for k in all_skills if k.startswith(slug)]
            if len(candidates) == 1:
                slug = candidates[0]
            elif not candidates:
                raise FileNotFoundError(
                    f"Skill '{name_or_path}' not found in any skills directory"
                )
            else:
                raise FileNotFoundError(
                    f"Ambiguous skill name '{name_or_path}' -- matches: {candidates}"
                )
        skill_path = all_skills[slug]

    if os.getenv("VECTOR_DISABLE_SKILL_SCANNER", "").lower() not in {"1", "true", "yes"}:
        try:
            from core.security.skill_scanner import scan_skill_for_load

            scan_report = scan_skill_for_load(skill_path)
            if scan_report.blocked:
                reasons = "; ".join(
                    f"{f.category}:{f.message}" for f in scan_report.findings[:3]
                )
                raise ValueError(
                    f"Skill '{name_or_path}' blocked by VECTOR skill scanner "
                    f"({scan_report.summary()}): {reasons}"
                )
        except ValueError:
            raise
        except Exception as exc:
            # Fail CLOSED: a malicious skill can deliberately crash the scanner
            # (e.g. malformed content that breaks the parser) to slip past the
            # gate. Treat any scanner error as a block. Operator can set
            # VECTOR_DISABLE_SKILL_SCANNER=1 to bypass if the scanner is genuinely
            # buggy. (Was: warn-and-load — a fail-open security gate.)
            logger.error(
                "[VECTOR][skills] skill scanner errored for {} — blocking (fail-closed): {}",
                skill_path, exc,
            )
            raise ValueError(
                f"Skill '{name_or_path}' blocked: scanner errored (fail-closed). "
                f"Set VECTOR_DISABLE_SKILL_SCANNER=1 to bypass if the scanner is buggy. ({exc})"
            ) from exc

    raw = skill_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(raw)

    # Platform compatibility check
    if not skill_matches_platform(frontmatter):
        raise ValueError(
            f"Skill '{name_or_path}' is not compatible with platform '{sys.platform}'"
        )

    skill_dir = skill_path.parent

    # Template substitution
    body = substitute_template_vars(body, skill_dir, session_id or None)

    # Inline shell expansion (only if explicitly enabled; off by default for safety)
    # Callers that want expansion should call expand_inline_shell directly.

    name = str(frontmatter.get("name") or skill_dir.name)
    description = str(frontmatter.get("description") or "").strip().strip("'\"")
    capabilities: List[str] = list(frontmatter.get("capabilities") or [])

    return {
        "name": name,
        "description": description,
        "body": body,
        "frontmatter": frontmatter,
        "path": skill_path,
        "capabilities": capabilities,
    }

# ── Formatting ────────────────────────────────────────────────────────────────

def format_skill_for_injection(skill: Dict[str, Any], user_instruction: str = "") -> str:
    """Format a loaded skill dict for injection as a system/user message.

    Header: [Skill: name] Description: ...
    Body:   preprocessed skill content
    Optional task appended when user_instruction is provided.
    """
    name = skill.get("name", "unknown")
    description = skill.get("description", "")
    body = skill.get("body", "")

    lines = [f"[Skill: {name}]"]
    if description:
        lines.append(f"Description: {description}")
    lines.append("")
    lines.append(body.strip())
    if user_instruction:
        lines.append("")
        lines.append(f"Task: {user_instruction}")
    return "\n".join(lines)

# ── SkillRegistry ─────────────────────────────────────────────────────────────

class SkillRegistry:
    """Thread-safe registry of all discoverable skills."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._skills: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def refresh(self) -> int:
        """Scan all skill directories and reload metadata. Returns skill count."""
        with self._lock:
            all_skill_paths = list_all_skills()
            new_skills: Dict[str, Dict[str, Any]] = {}
            for slug, skill_path in all_skill_paths.items():
                try:
                    raw = skill_path.read_text(encoding="utf-8")
                    frontmatter, _ = parse_frontmatter(raw)
                    if not skill_matches_platform(frontmatter):
                        continue
                    scan_summary = "not_scanned"
                    if os.getenv("VECTOR_DISABLE_SKILL_SCANNER", "").lower() not in {"1", "true", "yes"}:
                        try:
                            from core.security.skill_scanner import scan_skill_for_load

                            scan_report = scan_skill_for_load(skill_path)
                            scan_summary = scan_report.summary()
                            if scan_report.blocked:
                                logger.warning(
                                    "[VECTOR][skills] quarantined {}: {}",
                                    skill_path,
                                    scan_summary,
                                )
                                continue
                        except Exception as scan_exc:
                            scan_summary = f"scanner_error:{scan_exc}"
                            logger.warning(
                                "[VECTOR][skills] scanner failed for {}: {}",
                                skill_path,
                                scan_exc,
                            )
                    name = str(frontmatter.get("name") or skill_path.parent.name)
                    description = str(frontmatter.get("description") or "").strip().strip("'\"")
                    new_skills[slug] = {
                        "slug": slug,
                        "name": name,
                        "description": description,
                        "path": skill_path,
                        "frontmatter": frontmatter,
                        "scan": scan_summary,
                    }
                except Exception as e:
                    logger.debug(f"[VECTOR][skills] failed to load metadata for {skill_path}: {e}")
            self._skills = new_skills
            self._loaded = True
            logger.info(f"[VECTOR][skills] registry refreshed: {len(self._skills)} skills")
            return len(self._skills)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.refresh()

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a skill by name. Returns full skill dict or None."""
        self._ensure_loaded()
        try:
            return load_skill(name)
        except (FileNotFoundError, ValueError):
            return None

    def list(self) -> List[Dict[str, Any]]:
        """Return metadata for all registered skills (no body content)."""
        self._ensure_loaded()
        with self._lock:
            return [
                {k: v for k, v in skill.items() if k not in ("frontmatter",)}
                for skill in self._skills.values()
            ]

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Keyword search on name + description. Returns matching skill metadata."""
        self._ensure_loaded()
        keywords = [kw.lower() for kw in re.split(r"\W+", query) if len(kw) > 1]
        if not keywords:
            return self.list()
        results = []
        with self._lock:
            for skill in self._skills.values():
                haystack = (skill["name"] + " " + skill["description"]).lower()
                if any(kw in haystack for kw in keywords):
                    results.append({k: v for k, v in skill.items() if k != "frontmatter"})
        return results

# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    # parse_frontmatter
    raw = "---\nname: test-skill\ndescription: A test skill\n---\n# Body text\nsome content"
    fm, body = parse_frontmatter(raw)
    assert fm.get("name") == "test-skill", f"frontmatter name mismatch: {fm}"
    assert "Body text" in body, f"body missing: {body!r}"

    # parse_frontmatter -- no frontmatter
    fm2, body2 = parse_frontmatter("# Just a body\nno frontmatter here")
    assert fm2 == {}, f"expected empty frontmatter, got: {fm2}"
    assert "Just a body" in body2

    # skill_matches_platform
    assert skill_matches_platform({}) is True  # no platforms = all OK
    assert skill_matches_platform({"platforms": []}) is True
    assert skill_matches_platform({"platforms": ["windows"]}) == sys.platform.startswith("win32")
    assert skill_matches_platform({"platforms": ["linux", "windows"]}) == (
        sys.platform.startswith("linux") or sys.platform.startswith("win32")
    )

    # substitute_template_vars
    content = "Dir is ${VECTOR_SKILL_DIR} and session is ${VECTOR_SESSION_ID}."
    result = substitute_template_vars(content, Path("/tmp/myskill"), "sess-42")
    assert "/tmp/myskill" in result or "myskill" in result
    assert "sess-42" in result

    # substitute_template_vars -- unresolved tokens left in place
    result2 = substitute_template_vars(content, None, None)
    assert "${VECTOR_SKILL_DIR}" in result2
    assert "${VECTOR_SESSION_ID}" in result2

    # get_all_skills_dirs -- should return a list of Path objects
    dirs = get_all_skills_dirs()
    assert isinstance(dirs, list)

    # list_all_skills -- should return a dict
    all_skills = list_all_skills()
    assert isinstance(all_skills, dict)
    print(f"   found {len(all_skills)} installed skills")

    # SkillRegistry
    registry = SkillRegistry()
    count = registry.refresh()
    assert count == len(all_skills)
    assert isinstance(registry.list(), list)

    # search
    search_results = registry.search("memory")
    assert isinstance(search_results, list)

    # load_skill -- test with a real skill if available, otherwise confirm error
    if all_skills:
        first_slug = next(iter(all_skills))
        try:
            skill = load_skill(first_slug)
            assert "name" in skill
            assert "body" in skill
            assert "frontmatter" in skill
            assert "path" in skill
            assert isinstance(skill["capabilities"], list)
            formatted = format_skill_for_injection(skill, user_instruction="do something")
            assert "[Skill:" in formatted
            assert "Task: do something" in formatted
            print(f"   loaded skill: {skill['name']!r}")
        except ValueError:
            print(f"   skill '{first_slug}' skipped (platform incompatible)")
    else:
        # Test error on missing skill
        try:
            load_skill("nonexistent-skill-xyz")
            assert False, "should have raised FileNotFoundError"
        except FileNotFoundError as _sve:
            logger.warning("[VECTOR][skills.loader] suppressed FileNotFoundError: {}", _sve)

    # format_skill_for_injection -- no user_instruction
    skill_dict = {"name": "test", "description": "desc", "body": "skill body"}
    formatted = format_skill_for_injection(skill_dict)
    assert "[Skill: test]" in formatted
    assert "Task:" not in formatted

    print("skills/loader.py OK")

def discover_skills(search_path=None, *, include_optional: bool = False):
    """Discover available skills in search_path or default skill directories."""
    from pathlib import Path as _Path
    skills = []
    if search_path is None:
        search_path = _Path(__file__).parent / 'builtin'
    search_path = _Path(search_path)
    if search_path.exists():
        for toml in search_path.rglob('skill.toml'):
            skills.append({'path': str(toml.parent), 'name': toml.parent.name})
    if include_optional:
        opt = _Path(__file__).parent / 'optional'
        if opt.exists():
            for toml in opt.rglob('skill.toml'):
                skills.append({'path': str(toml.parent), 'name': toml.parent.name})
    return skills

def load_skill_directory(path=None) -> list:
    """Load skills from a directory."""
    return discover_skills(search_path=path)
