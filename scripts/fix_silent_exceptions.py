"""
Fix silent exception swallows in vectorcode/src.
Strategy:
  - Files WITH 'from loguru import logger': add logger.debug/warning logging
  - Files WITHOUT loguru: add 'from loguru import logger' at top (line 1 or after shebang/encoding)
  - asyncio.CancelledError: always re-raise (never swallow)
  - ImportError / ModuleNotFoundError: keep as pass (optional deps)
  - (SystemExit, KeyboardInterrupt): keep as pass
  - WebSocketDisconnect, AuthError: keep as pass (framework signals)
  - Shutdown context CancelledError already commented — skip

Run: python -X utf8 scripts/fix_silent_exceptions.py
"""
import pathlib, re, sys, ast

ROOT = pathlib.Path(__file__).parent.parent / "vectorcode" / "src"

SKIP_TYPES = {
    "ImportError", "ModuleNotFoundError",
    "SystemExit", "KeyboardInterrupt",
    "(SystemExit, KeyboardInterrupt)",
    "(ValueError, KeyboardInterrupt, EOFError)",
    "WebSocketDisconnect", "AuthError", "image_not_found",
    # CancelledError handled separately (must raise)
}

KEEP_PASS_COMMENT = "# intentional:"  # already-annotated lines — don't touch

def log_level(exc_str: str) -> str:
    exc = exc_str.strip()
    os_errors = {
        "OSError", "PermissionError", "FileNotFoundError",
        "ProcessLookupError", "BrokenPipeError",
        "(OSError, IOError)", "(FileNotFoundError, PermissionError, OSError)",
        "(OSError, FileNotFoundError)", "(PermissionError, OSError)",
        "(FileNotFoundError, OSError, ValueError)", "(OSError, ValueError)",
        "(OSError, PermissionError)", "(ProcessLookupError, PermissionError, OSError)",
        "(ProcessLookupError, PermissionError)", "(ProcessLookupError, OSError)",
        "(BrokenPipeError, OSError)", "(ProcessLookupError, ChildProcessError)",
        "subprocess.CalledProcessError", "(FileNotFoundError, subprocess.TimeoutExpired)",
        "(OSError, subprocess.TimeoutExpired)", "(RuntimeError, subprocess.TimeoutExpired)",
        "(FileNotFoundError, subprocess.TimeoutExpired, ImportError)",
        "(ImportError, NotImplementedError, OSError, subprocess.SubprocessError)",
    }
    return "warning" if exc in os_errors else "debug"


def insert_loguru_at_top(src: str) -> str:
    """Add 'from loguru import logger' at the very first non-shebang, non-encoding line."""
    lines = src.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#!") or stripped.startswith("# -*-") or stripped.startswith("# coding"):
            insert_at = i + 1
        elif stripped.startswith('"""') or stripped.startswith("'''") or stripped.startswith("#"):
            # Skip module docstrings and top-level comments
            if i < 5:
                insert_at = i + 1
        else:
            break
    lines.insert(insert_at, "from loguru import logger\n")
    return "".join(lines)


def fix_file(path: pathlib.Path) -> tuple[int, str]:
    """Returns (changes_count, new_content)."""
    src = path.read_text(encoding="utf-8", errors="replace")

    # Derive module tag from relative path
    try:
        rel = path.relative_to(ROOT)
        module_tag = str(rel).replace("\\", "/").replace(".py", "").replace("/", ".")
    except ValueError:
        module_tag = path.stem

    has_logger = "from loguru import logger" in src

    lines = src.splitlines(keepends=True)
    changes = 0
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n\r")
        lstripped = stripped.lstrip()

        if lstripped.startswith("except ") or lstripped.startswith("except:"):
            indent = len(stripped) - len(lstripped)
            body_indent = " " * (indent + 4)

            # Extract exception type
            if lstripped.startswith("except:"):
                exc_type = "Exception"
            else:
                m = re.match(r'except\s+(.*?)\s*(?:as\s+\w+\s*)?:', lstripped)
                exc_type = m.group(1).strip() if m else ""

            # Handle asyncio.CancelledError — always re-raise
            if "CancelledError" in exc_type and "asyncio.TimeoutError" not in exc_type:
                # Check next non-empty line
                j = i + 1
                while j < len(lines) and lines[j].strip() in ("", ):
                    j += 1
                if j < len(lines) and lines[j].strip() == "pass":
                    # Check not already annotated
                    if KEEP_PASS_COMMENT not in lines[j]:
                        new_lines.append(line)
                        for k in range(i + 1, j):
                            new_lines.append(lines[k])
                        new_lines.append(f"{body_indent}raise  # must propagate for asyncio to work\n")
                        changes += 1
                        i = j + 1
                        continue

            # Skip types that should stay silent
            if exc_type in SKIP_TYPES:
                new_lines.append(line)
                i += 1
                continue

            # Check next non-empty line for `pass`
            j = i + 1
            found_pass = False
            pass_line_idx = -1
            while j < len(lines):
                ns = lines[j].rstrip("\n\r").strip()
                if ns == "" or ns.startswith("#"):
                    j += 1
                    continue
                if ns == "pass":
                    # Check not already annotated as intentional
                    if KEEP_PASS_COMMENT not in lines[j]:
                        found_pass = True
                        pass_line_idx = j
                break

            if found_pass:
                level = log_level(exc_type)
                log_stmt = f'{body_indent}logger.{level}("[VECTOR][{module_tag}] suppressed {exc_type}: %s", _sve)\n'

                # Add `as _sve` to the except clause if not already there
                new_except = re.sub(
                    r'^(\s*except\s+)(.*?)(\s*:\s*)$',
                    lambda m: f'{m.group(1)}{m.group(2)} as _sve{m.group(3)}',
                    stripped
                )
                if "except:" in stripped:
                    new_except = stripped.replace("except:", "except Exception as _sve:", 1)

                new_lines.append(new_except + "\n")
                for k in range(i + 1, pass_line_idx):
                    new_lines.append(lines[k])
                new_lines.append(log_stmt)
                changes += 1
                i = pass_line_idx + 1
                continue

        new_lines.append(line)
        i += 1

    new_src = "".join(new_lines)

    # Add loguru import if changes were made and it's not there
    if changes > 0 and not has_logger:
        new_src = insert_loguru_at_top(new_src)

    return changes, new_src


def main():
    total_files = 0
    total_changes = 0
    syntax_errors = []

    py_files = list(ROOT.rglob("*.py"))
    print(f"Scanning {len(py_files)} files in vectorcode/src ...")

    for path in py_files:
        try:
            changes, new_src = fix_file(path)
            if changes > 0:
                # Verify syntax before writing
                try:
                    ast.parse(new_src)
                except SyntaxError as se:
                    syntax_errors.append((str(path.relative_to(ROOT)), str(se)))
                    continue  # Skip writing this file
                path.write_text(new_src, encoding="utf-8")
                total_files += 1
                total_changes += changes
        except Exception as e:
            syntax_errors.append((str(path), str(e)))

    print(f"\n{'='*55}")
    print(f"  Fixed {total_changes} silent exceptions in {total_files} files")
    if syntax_errors:
        print(f"  Skipped (syntax errors): {len(syntax_errors)}")
        for fp, err in syntax_errors[:20]:
            print(f"    {fp}: {err}")
    print(f"{'='*55}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
