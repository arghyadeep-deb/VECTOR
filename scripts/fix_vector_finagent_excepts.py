"""
Fix bare except: blocks in vector_finagent.
Uses indentation-aware parser to find handler body boundaries.
"""
import ast
import pathlib
import sys
import re

ROOT = pathlib.Path(__file__).parent.parent / "districts" / "investment" / "vector_finagent"


def find_handler_end(lines, start_idx, indent):
    """Return index of first line AFTER the handler body.
    Handler body starts at start_idx, ends when indentation <= indent.
    """
    i = start_idx
    while i < len(lines):
        raw = lines[i]
        lstripped = raw.lstrip()
        if lstripped == "" or lstripped.startswith("#"):
            i += 1
            continue
        leading = len(raw) - len(lstripped)
        if leading <= indent:
            break
        i += 1
    return i


def fix_file(path):
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        ast.parse(src)
    except SyntaxError:
        return 0, src

    has_logger = "from loguru import logger" in src
    try:
        rel = path.relative_to(ROOT)
        module_tag = str(rel).replace("\\", "/").replace(".py", "").replace("/", ".")
    except ValueError:
        module_tag = path.stem

    lines = src.splitlines(keepends=True)
    changes = 0
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n\r")
        lstripped = stripped.lstrip()

        if lstripped.startswith("except:"):
            indent = len(stripped) - len(lstripped)
            body_indent = " " * (indent + 4)
            handler_end = find_handler_end(lines, i + 1, indent)

            # Grab body lines
            body_lines = lines[i + 1:handler_end]

            # Check if handler body is effectively just pass (with optional comment)
            is_pass_only = True
            has_code = False
            for bl in body_lines:
                bls = bl.strip()
                if bls == "" or bls.startswith("#"):
                    continue
                if re.match(r'^pass\b', bls):
                    has_code = True
                else:
                    is_pass_only = False
                    break

            if is_pass_only and has_code:
                log_stmt = f'{body_indent}logger.warning("[VECTOR][{module_tag}] suppressed Exception")  # bare except\n'
                new_except_line = f"{' ' * indent}except Exception:\n"
                new_lines.append(new_except_line)
                new_lines.append(log_stmt)
                changes += 1
                i = handler_end
                continue
            elif not is_pass_only:
                log_stmt = f'{body_indent}logger.debug("[VECTOR][{module_tag}] suppressed Exception in fallback")  # bare except\n'
                new_except_line = f"{' ' * indent}except Exception:\n"
                new_lines.append(new_except_line)
                new_lines.append(log_stmt)
                changes += 1
                i = handler_end
                continue

        new_lines.append(line)
        i += 1

    new_src = "".join(new_lines)

    if changes > 0 and not has_logger:
        new_src = insert_loguru_at_top(new_src)

    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {path.relative_to(ROOT)}: {e}", file=sys.stderr)
        return 0, src

    return changes, new_src


def insert_loguru_at_top(src):
    lines = src.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#!") or s.startswith("# -*-") or s.startswith("# coding"):
            insert_at = i + 1
        elif (s.startswith('"""') or s.startswith("'''") or s.startswith("#")) and i < 5:
            insert_at = i + 1
        else:
            break
    lines.insert(insert_at, "from loguru import logger\n")
    return "".join(lines)


def main():
    py_files = list(ROOT.rglob("*.py"))
    print(f"Scanning {len(py_files)} files ...")
    total_files = 0
    total_changes = 0
    errors = []

    for path in py_files:
        try:
            changes, new_src = fix_file(path)
            if changes > 0:
                path.write_text(new_src, encoding="utf-8")
                total_files += 1
                total_changes += changes
        except Exception as e:
            errors.append((str(path), str(e)))

    print(f"\n{'='*55}")
    print(f"  Fixed {total_changes} silent exceptions in {total_files} files")
    if errors:
        print(f"  Errors: {len(errors)}")
        for fp, err in errors[:10]:
            print(f"    {fp}: {err}")
    print(f"{'='*55}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
