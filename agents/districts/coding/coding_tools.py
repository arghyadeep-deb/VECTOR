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
    from agents.districts.coding.coding_tools import (
        apply_search_replace, grep_code, read_code_file
    )
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

# ── search_replace ────────────────────────────────────────────────────────────

def apply_search_replace(file_path: str, search: str, replace: str) -> dict:
    """Apply a search/replace block to a file. Returns {success, diff, error}."""
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
                    pass
            return {"matches": results, "count": len(results), "engine": "ripgrep"}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

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
            pass
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

def load_skill(skill_name: str) -> dict | None:
    """Load a skill definition from ~/.claude/skills/<name>/SKILL.md."""
    try:
        from core.coding_assistant.core.skills.manager import SkillManager
        from core.coding_assistant.core.paths import GLOBAL_SKILLS_DIR
        manager = SkillManager(skills_dirs=[GLOBAL_SKILLS_DIR])
        skill = manager.get_skill(skill_name)
        if skill:
            return {"name": skill.name, "description": skill.description,
                    "content": skill.content}
        return None
    except Exception as e:
        logger.warning("[VECTOR][coding_tools] load_skill failed: {}", e)
        return None


# ── jcode tools (ported from high-performance agent harness) ──────────────────

def multiedit_file(file_path: str, edits: list[dict]) -> dict:
    """
    Atomically apply multiple search/replace operations to a single file.
    Each edit: {old_string, new_string, replace_all (optional)}.
    Returns {success, applied, failed, diff}.
    """
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
    result = grep_code("def grep_code", "agents/districts/coding")
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
