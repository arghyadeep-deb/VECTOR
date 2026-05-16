"""
Fix silent exception swallows in vectorcode/src.
Rules:
  - ImportError: pass → keep as-is (optional deps)
  - asyncio.CancelledError → already fixed (must raise)
  - Exception: pass → add logger.debug
  - OSError: pass → add logger.warning
  - ValueError: pass → add logger.debug
  - Others (FileNotFoundError, subprocess.*, etc.) → add logger.debug
  - (SystemExit, KeyboardInterrupt): pass → keep as-is
  - WebSocketDisconnect: pass → keep as-is (framework-level signal)
  - curses.error: pass → add logger.debug (TUI optional)
Run: python -X utf8 scripts/fix_silent_exceptions.py
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).parent.parent / "vectorcode" / "src"

# Exception types to SKIP (leave as pass)
SKIP_TYPES = {
    "ImportError",
    "ModuleNotFoundError",
    "asyncio.CancelledError",
    "SystemExit",
    "KeyboardInterrupt",
    "(SystemExit, KeyboardInterrupt)",
    "WebSocketDisconnect",
    "AuthError",
    "image_not_found",
    "(asyncio.CancelledError, asyncio.TimeoutError)",  # shutdown context, already commented
}

# Exception types → log level mapping
def log_level(exc_str: str) -> str:
    exc = exc_str.strip()
    if exc in ("OSError", "PermissionError", "FileNotFoundError",
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
               "ProcessLookupError"):
        return "warning"
    return "debug"

# Regex: match `except <type>:` followed by `    pass` on next line
# We'll process line by line for precision
def fix_file(path: pathlib.Path) -> tuple[int, str]:
    """Returns (changes_count, new_content)"""
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines(keepends=True)

    # Derive a module name for the log tag
    try:
        rel = path.relative_to(ROOT)
        module_tag = str(rel).replace("\\", "/").replace(".py", "").replace("/", ".")
    except ValueError:
        module_tag = path.stem

    # Check if loguru is already imported
    has_logger = "from loguru import logger" in src or "import logger" in src

    changes = 0
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n\r")
        lstripped = stripped.lstrip()

        if lstripped.startswith("except ") or lstripped.startswith("except:"):
            # Determine indent level of this except clause
            indent = len(stripped) - len(lstripped)
            except_indent = " " * indent
            body_indent = " " * (indent + 4)

            # Extract exception type
            if lstripped.startswith("except:"):
                exc_type = "Exception"
            else:
                # "except Foo:" or "except (Foo, Bar):"
                m = re.match(r'except\s+(.*?)\s*(?:as\s+\w+\s*)?:', lstripped)
                exc_type = m.group(1).strip() if m else ""

            # Check if the NEXT non-empty line is just `pass`
            # Collect all next lines
            j = i + 1
            found_pass = False
            pass_line_idx = -1

            while j < len(lines):
                next_stripped = lines[j].rstrip("\n\r").strip()
                if next_stripped == "" or next_stripped.startswith("#"):
                    j += 1
                    continue
                if next_stripped == "pass":
                    found_pass = True
                    pass_line_idx = j
                break

            if found_pass and exc_type not in SKIP_TYPES:
                level = log_level(exc_type)
                # Replace `pass` with `logger.debug/warning(...)`
                log_stmt = f'{body_indent}logger.{level}("[VECTOR][{module_tag}] suppressed {exc_type}: %s", _sve)\n'

                # Modify the except line to capture exception
                # except Foo: → except Foo as _sve:
                new_except_line = re.sub(
                    r'^(\s*except\s+.*?)(\s*as\s+\w+)?(\s*:)',
                    lambda m: f'{m.group(1)} as _sve{m.group(3)}',
                    stripped
                )
                if new_except_line == stripped:
                    # bare `except:`
                    new_except_line = stripped.replace("except:", "except Exception as _sve:", 1)

                new_lines.append(new_except_line + "\n")
                # Add all comment lines between except and pass
                for k in range(i + 1, pass_line_idx):
                    new_lines.append(lines[k])
                # Replace pass with logger call
                new_lines.append(log_stmt)
                changes += 1
                i = pass_line_idx + 1
                continue

        new_lines.append(line)
        i += 1

    new_src = "".join(new_lines)

    # Add loguru import if we made changes and it's not already there
    if changes > 0 and not has_logger:
        # Find a good place to insert — after the last import block
        import_end = 0
        for idx, ln in enumerate(new_src.splitlines()):
            stripped_ln = ln.strip()
            if stripped_ln.startswith("import ") or stripped_ln.startswith("from "):
                import_end = idx

        # Insert after last import
        src_lines = new_src.splitlines(keepends=True)
        insert_idx = import_end + 1
        src_lines.insert(insert_idx, "from loguru import logger\n")
        new_src = "".join(src_lines)

    return changes, new_src


def main():
    total_files = 0
    total_changes = 0
    errored = []

    py_files = list(ROOT.rglob("*.py"))
    print(f"Scanning {len(py_files)} files in vectorcode/src ...")

    for path in py_files:
        try:
            changes, new_src = fix_file(path)
            if changes > 0:
                path.write_text(new_src, encoding="utf-8")
                total_files += 1
                total_changes += changes
                print(f"  [{changes:3d} fixes] {path.relative_to(ROOT.parent.parent)}")
        except Exception as e:
            errored.append((str(path), str(e)))

    print(f"\n{'='*55}")
    print(f"  Fixed {total_changes} silent exceptions in {total_files} files")
    if errored:
        print(f"  Errors ({len(errored)}):")
        for fp, err in errored[:10]:
            print(f"    {fp}: {err}")
    print(f"{'='*55}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
