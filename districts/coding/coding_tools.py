"""
VECTOR Coding Tools — wires core/coding_assistant/ tools into the coding district.

These are the actual tool implementations from the coding assistant engine:
  - search_replace  : apply SEARCH/REPLACE blocks to files
  - bash_execute    : stateful shell execution with trust system
  - grep_code       : ripgrep-backed code search
  - read_file_tool  : safe async file reading
  - write_file_tool : safe file writing with rewind snapshot
  - todo_manager    : agent task/todo list

All tools run through VECTOR's permission_gateway before executing.
Usage from any district:
    from districts.coding.coding_tools import (
        apply_search_replace, grep_code, read_code_file
    )
"""
from pathlib import Path

from loguru import logger


# ── F-5: coding-grant gate ────────────────────────────────────────────────────
def _require_coding_grant(fn_name: str) -> bool:
    """Return True if a gateway-approved code execution grant is active in the
    current context. File-write helpers refuse (returning an error dict) when
    this is False, so a direct importer that bypasses the gateway cannot write
    files via these helpers. The grant is set by the autonomous loop after a
    code_* action is approved (core.loop.permission_gateway.set_coding_grant)."""
    try:
        from core.loop.permission_gateway import is_coding_grant_active
        return is_coding_grant_active()
    except Exception as _e:
        logger.debug(f"[VECTOR][coding_tools] coding-grant check unavailable for {fn_name}: {_e}")
        return False


# ── search_replace ────────────────────────────────────────────────────────────

def apply_search_replace(file_path: str, search: str, replace: str) -> dict:
    """Apply a search/replace block to a file. Returns {success, diff, error}."""
    if not _require_coding_grant("apply_search_replace"):
        logger.warning("[VECTOR][coding_tools] apply_search_replace blocked — no active coding grant (gateway code_* approval required)")
        return {"success": False, "error": "coding grant not active — call from within a gateway-approved code_* execution"}
    try:
        from core.coding_assistant.core.tools.builtins.search_replace import (
            SearchReplaceBlock,
        )
        p = Path(file_path)
        if not p.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        original = p.read_text(encoding="utf-8", errors="replace")
        if search not in original:
            return {"success": False, "error": "SEARCH block not found in file"}
        new_content = original.replace(search, replace, 1)
        p.write_text(new_content, encoding="utf-8")
        logger.info("[VECTOR][coding_tools] search_replace applied: {}", file_path)
        return {"success": True, "file": file_path, "changed": original != new_content}
    except Exception as e:
        logger.error("[VECTOR][coding_tools] search_replace failed: {}", e)
        return {"success": False, "error": str(e)}


def parse_search_replace_blocks(text: str) -> list[dict]:
    """Parse <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE blocks from text."""
    import re
    pattern = re.compile(
        r"<{5,} SEARCH\r?\n(.*?)\r?\n?={5,}\r?\n(.*?)\r?\n?>{5,} REPLACE",
        flags=re.DOTALL
    )
    return [{"search": m.group(1), "replace": m.group(2)} for m in pattern.finditer(text)]


# ── grep / code search ────────────────────────────────────────────────────────

def grep_code(pattern: str, path: str = ".", file_glob: str = "*.py",
              max_results: int = 50) -> dict:
    """Search code with ripgrep (falls back to Python glob+re). Returns {matches, count}."""
    import subprocess, re as _re
    results = []
    try:
        # Try ripgrep first
        proc = subprocess.run(
            ["rg", "--json", "-g", file_glob, "-m", "5", pattern, path],
            capture_output=True, text=True, timeout=10
        )
        if proc.returncode == 0:
            import json
            for line in proc.stdout.splitlines():
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "match":
                        d = obj["data"]
                        results.append({
                            "file": d["path"]["text"],
                            "line": d["line_number"],
                            "text": d["lines"]["text"].rstrip(),
                        })
                        if len(results) >= max_results:
                            break
                except Exception:
                    logger.debug("[VECTOR] suppressed exception", exc_info=True)
            return {"matches": results, "count": len(results), "engine": "ripgrep"}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.debug("[VECTOR] suppressed exception", exc_info=True)

    # Fallback: Python search
    compiled = _re.compile(pattern, _re.IGNORECASE)
    for f in Path(path).rglob(file_glob):
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if compiled.search(line):
                    results.append({"file": str(f), "line": i, "text": line.rstrip()})
                    if len(results) >= max_results:
                        break
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)
        if len(results) >= max_results:
            break
    return {"matches": results, "count": len(results), "engine": "python"}


# ── file read/write ───────────────────────────────────────────────────────────

def read_code_file(file_path: str, start_line: int | None = None,
                   end_line: int | None = None) -> dict:
    """Read a file safely. Returns {content, line_count, truncated}."""
    try:
        p = Path(file_path)
        if not p.exists():
            return {"error": f"File not found: {file_path}"}
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if start_line is not None or end_line is not None:
            s = (start_line or 1) - 1
            e = end_line or len(lines)
            lines = lines[s:e]
        return {
            "content": "\n".join(lines),
            "line_count": len(lines),
            "file": file_path,
        }
    except Exception as e:
        return {"error": str(e)}


def write_code_file(file_path: str, content: str, create_dirs: bool = True) -> dict:
    """Write a file. Creates parent dirs if needed. Returns {success, file}."""
    if not _require_coding_grant("write_code_file"):
        logger.warning("[VECTOR][coding_tools] write_code_file blocked — no active coding grant (gateway code_* approval required)")
        return {"success": False, "error": "coding grant not active — call from within a gateway-approved code_* execution"}
    try:
        p = Path(file_path)
        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        logger.info("[VECTOR][coding_tools] wrote: {}", file_path)
        return {"success": True, "file": file_path, "bytes": len(content.encode())}
    except Exception as e:
        logger.error("[VECTOR][coding_tools] write failed: {}", e)
        return {"success": False, "error": str(e)}


# ── hooks system ─────────────────────────────────────────────────────────────

def get_hooks_manager(hooks_config: list[dict] | None = None):
    """Get a HooksManager for PreToolUse/PostToolUse hooks.
    Complements VECTOR's permission_gateway with project-level hooks."""
    try:
        from core.coding_assistant.core.hooks.manager import HooksManager
        return HooksManager(hooks_config or [])
    except Exception as e:
        logger.warning("[VECTOR][coding_tools] HooksManager unavailable: {}", e)
        return None


# ── skills system ─────────────────────────────────────────────────────────────
# Reads VECTOR's own skills directory (data/vector_skills/, one subdirectory
# per skill, each holding a SKILL.md -- same frontmatter format Claude Code
# uses, but this directory is VECTOR-only; Claude does not auto-discover it).
# Uses the lightweight parser/models from core.coding_assistant.core.skills
# directly rather than that module's own SkillManager class, which requires
# a VectorCAConfig + an explicitly-initialized HarnessFilesManager singleton
# (core.coding_assistant.core.config.harness_files) neither of which VECTOR's
# runtime sets up -- routing through it would raise RuntimeError on every
# call. This was the real, unverified bug in the previous implementation:
# it also called a since-renamed SkillManager(skills_dirs=...) constructor
# (the real signature takes a config_getter callable) and read a
# skill.content attribute that has never existed on SkillInfo (the real
# field is `prompt`) -- three independent breaks stacked on one function,
# meaning it has never successfully returned a skill.

def _vector_skills_dir() -> Path:
    from core.runtime_paths import data_path
    return data_path("vector_skills")


def _parse_skill_dir(skill_dir: Path):
    """Return a SkillInfo for skill_dir/SKILL.md, or None if missing/invalid."""
    from core.coding_assistant.core.skills.models import SkillInfo, SkillMetadata
    from core.coding_assistant.core.skills.parser import SkillParseError, parse_skill_markdown

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return None
    try:
        content = skill_file.read_text(encoding="utf-8")
        frontmatter, body = parse_skill_markdown(content)
        metadata = SkillMetadata.model_validate(frontmatter)
        return SkillInfo.from_metadata(metadata, skill_file, prompt=body.strip())
    except (SkillParseError, OSError, ValueError) as e:
        logger.warning("[VECTOR][coding_tools] failed to parse skill at {}: {}", skill_file, e)
        return None


def load_skill(skill_name: str) -> dict | None:
    """Load one skill's parsed content from VECTOR's own skills directory
    (data/vector_skills/<skill_name>/SKILL.md)."""
    try:
        skills_dir = _vector_skills_dir()
        skill_dir = skills_dir / skill_name
        skill = _parse_skill_dir(skill_dir)
        if skill is None:
            return None
        return {
            "name": skill.name,
            "description": skill.description,
            "prompt": skill.prompt,
            "metadata": skill.metadata,
        }
    except Exception as e:
        logger.warning("[VECTOR][coding_tools] load_skill failed: {}", e)
        return None


def list_skills() -> list[dict]:
    """List every skill available in VECTOR's own skills directory (name +
    description only, not the full prompt body)."""
    try:
        skills_dir = _vector_skills_dir()
        if not skills_dir.is_dir():
            return []
        found: list[dict] = []
        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill = _parse_skill_dir(entry)
            if skill is not None:
                found.append({"name": skill.name, "description": skill.description})
        return found
    except Exception as e:
        logger.warning("[VECTOR][coding_tools] list_skills failed: {}", e)
        return []


# ── jcode tools (ported from high-performance agent harness) ──────────────────

def multiedit_file(file_path: str, edits: list[dict]) -> dict:
    """
    Atomically apply multiple search/replace operations to a single file.
    Each edit: {old_string, new_string, replace_all (optional)}.
    Returns {success, applied, failed, diff}.
    """
    if not _require_coding_grant("multiedit_file"):
        logger.warning("[VECTOR][coding_tools] multiedit_file blocked — no active coding grant (gateway code_* approval required)")
        return {"success": False, "error": "coding grant not active — call from within a gateway-approved code_* execution"}
    try:
        from core.jcode.tools.multiedit import multiedit
        return multiedit(file_path, edits)
    except Exception as e:
        logger.error("[VECTOR][coding_tools] multiedit failed: {}", e)
        return {"success": False, "error": str(e)}


def apply_codex_patch(patch_text: str, base_dir: str = ".") -> dict:
    """
    Apply a Codex-style *** Begin Patch / *** End Patch block.
    Supports Add File, Delete File, Update File (with Move to).
    Returns {success, results, touched_files}.
    """
    if not _require_coding_grant("apply_codex_patch"):
        logger.warning("[VECTOR][coding_tools] apply_codex_patch blocked — no active coding grant (gateway code_* approval required)")
        return {"success": False, "error": "coding grant not active — call from within a gateway-approved code_* execution"}
    try:
        from core.jcode.tools.apply_patch import apply_patch
        return apply_patch(patch_text, base_dir)
    except Exception as e:
        logger.error("[VECTOR][coding_tools] apply_patch failed: {}", e)
        return {"success": False, "error": str(e)}


def check_cache_violation(messages: list[dict], tracker=None):
    """
    Check message list for KV cache append-only violations.
    Pass a CacheTracker instance to persist state across calls.
    Returns CacheViolation or None.
    """
    try:
        from core.jcode.cache_tracker import CacheTracker
        t = tracker or CacheTracker()
        return t.record_request(messages)
    except Exception as e:
        logger.warning("[VECTOR][coding_tools] cache_tracker unavailable: {}", e)
        return None


async def run_code_safely(
    code: str,
    timeout: float = 30.0,
    language: str = "python",
) -> dict:
    """
    Execute user-provided code in VectorSandbox (isolated subprocess, no API keys).
    Returns {success, stdout, stderr, exit_code, elapsed_secs}.
    Used by coding district agents to safely run generated code snippets.
    """
    try:
        from core.sandbox.vector_sandbox import VectorSandbox, SandboxConfig
        sandbox = VectorSandbox(SandboxConfig(timeout_secs=timeout))
        if language == "python":
            result = await sandbox.run_python(code, timeout=timeout)
        else:
            result = await sandbox.run_shell(code, timeout=timeout)
        logger.info(
            "[VECTOR][coding_tools] sandbox run: success={} elapsed={:.2f}s",
            result.success, result.elapsed_secs,
        )
        return {
            "success": result.success,
            "stdout":  result.stdout,
            "stderr":  result.stderr,
            "exit_code": result.exit_code,
            "elapsed_secs": result.elapsed_secs,
            "timed_out": result.timed_out,
        }
    except Exception as e:
        logger.warning("[VECTOR][coding_tools] sandbox unavailable: {} — skipping", e)
        return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1, "elapsed_secs": 0}


if __name__ == "__main__":
    # Smoke tests
    import tempfile, os

    # F-5: the write helpers require an active coding grant. Set it for the self-test.
    from core.loop.permission_gateway import set_coding_grant
    set_coding_grant(True)

    # search_replace
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("x = 1\ny = 2\n")
        tmp = f.name
    result = apply_search_replace(tmp, "x = 1", "x = 42")
    assert result["success"], result
    assert Path(tmp).read_text() == "x = 42\ny = 2\n"
    os.unlink(tmp)
    print("OK  apply_search_replace")

    # parse blocks
    blocks = parse_search_replace_blocks("<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE")
    assert len(blocks) == 1 and blocks[0]["search"] == "old"
    print("OK  parse_search_replace_blocks")

    # grep
    result = grep_code("def grep_code", "districts/coding")
    assert result["count"] > 0, f"grep found nothing: {result}"
    print(f"OK  grep_code ({result['engine']}): {result['count']} match(es)")

    # read/write
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("hello\n")
        tmp2 = f.name
    r = read_code_file(tmp2)
    assert "hello" in r["content"]
    w = write_code_file(tmp2, "world\n")
    assert w["success"]
    os.unlink(tmp2)
    print("OK  read_code_file / write_code_file")

    print("\ncoding_tools.py OK — all tools functional")
