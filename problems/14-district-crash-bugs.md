# Problem 14 — District Crash Bugs (bug_hunter + architect_bot)

**Severity: HIGH**
**Status: bug_hunter FIXED; architect_bot DOCUMENTED**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Part A — bug_hunter.py: _find_pattern_issues AttributeError (FIXED)

### Symptom

`BugHunter.scan_file()` raises:

```
AttributeError: 'BugHunter' object has no attribute '_find_pattern_issues'
```

### Root Cause

`scan_file()` line 103 calls `self._find_pattern_issues(source_path)` (private,
leading underscore). The actual method is `find_pattern_issues()` (public, no
underscore) defined at line 193.

### Fix Applied

`agents/districts/coding/bug_hunter.py` line 103:

```python
# Before
bugs["pattern_bugs"] = self._find_pattern_issues(source_path)

# After
bugs["pattern_bugs"] = self.find_pattern_issues(str(source_path))
```

Also added `str()` conversion since `source_path` is a `Path` object and
`find_pattern_issues` expects a string filepath.

---

## Part B — architect_bot.py: Circular Import Logic Flawed (DOCUMENTED)

### Symptom

The circular import detector in `ArchitectBot.scan_codebase()` produces
false positives — it flags non-local imports as potential circular imports.

### Root Cause

`agents/districts/coding/architect_bot.py` line 75:

```python
if node.level > 0 or (node.module and not node.module.startswith("core") is False):
```

The expression `not node.module.startswith("core") is False` is evaluated
as `not (node.module.startswith("core") is False)` due to Python operator
precedence. This is equivalent to `bool(node.module.startswith("core"))` —
the `not ... is False` double-negative cancels out. The full condition
always includes every import regardless of whether it's local, making
`circular_candidates` contain all imports.

### Fix Required

`agents/districts/coding/architect_bot.py` line ~75:

```python
# Before (logically broken)
if node.level > 0 or (node.module and not node.module.startswith("core") is False):
    local_imports[module_path.stem].add(node.module)

# After (correct intent: track relative imports and core-prefixed imports)
is_relative = node.level > 0
is_local_absolute = node.module and node.module.startswith("core")
if is_relative or is_local_absolute:
    local_imports[module_path.stem].add(node.module or "")
```
