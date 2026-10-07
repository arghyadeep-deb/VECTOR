# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/pre_write_check.py

#!/usr/bin/env python3
"""
VECTOR Pre-Write Hook — fires before every Edit/Write tool call.
Blocks writes that would introduce syntax errors into Python files.
Exit 2 = block. Exit 0 = allow.
"""
from loguru import logger
import json
import os
import sys
import py_compile
import tempfile

try:
    data = json.loads(sys.stdin.read() or "{}")
except Exception:
    data = {}

file_path = data.get("file_path", os.environ.get("CLAUDE_TOOL_INPUT_FILE_PATH", ""))
new_content = data.get("content", "")

if not file_path or not file_path.endswith(".py"):
    sys.exit(0)

# If content is being written, validate it
if new_content:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(new_content)
            tmp_path = tmp.name
        py_compile.compile(tmp_path, doraise=True)
    except py_compile.PyCompileError as e:
        print(f"[VECTOR HOOK] Syntax error blocked write to {file_path}:\n{e}")
        sys.exit(2)
    except Exception:
        logger.opt(exception=True).debug("[VECTOR] suppressed exception")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

sys.exit(0)
