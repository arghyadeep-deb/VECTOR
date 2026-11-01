"""VECTOR per-district smoke (roadmap #9).

For every district under districts/, import each module and classify the result:

  PASS  — module imported cleanly
  SKIP  — failed only because an OPTIONAL third-party dependency is absent
          (e.g. playwright, instagrapi) — not a code defect
  FAIL  — real breakage: syntax error, broken core/districts/vectorcode import,
          NameError, etc. These block the district from loading at runtime.

This is a load-time wiring smoke (no agent instantiation → no side effects), so
it is safe to run anywhere and catches the most common "district is broken"
failure: an import that throws the moment the autonomous loop touches it.

Run:  python -X utf8 scripts/district_smoke.py
Exit: non-zero if any district has a FAIL.
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

DISTRICTS_DIR = _REPO / "districts"

# Modules that ship inside this repo — a failure to import these is a REAL bug.
_FIRST_PARTY = ("core", "districts", "vectorcode")


def _is_optional_dep_error(exc: BaseException) -> str | None:
    """Return the missing optional dependency name, or None if the failure is a
    genuine code defect we must surface."""
    if isinstance(exc, ModuleNotFoundError) and exc.name:
        top = exc.name.split(".")[0]
        if top not in _FIRST_PARTY and top not in sys.stdlib_module_names:
            return exc.name
    return None


def _iter_district_modules(district_dir: Path):
    """Yield the district's first-class agent modules — direct .py children only.

    These are the modules VECTOR's registry/governor actually imports. Deeper
    trees belong to vendored standalone subprojects (vector_finagent,
    vector_backtest, shadowbroker_server, ads/scripts, …) which carry their own
    package root + CLI entry scripts and are reached via a depth-1 adapter."""
    for py in sorted(district_dir.glob("*.py")):
        if py.name.startswith("test_") or py.name == "conftest.py":
            continue
        parts = py.relative_to(_REPO).with_suffix("").parts
        if py.name == "__init__.py":
            mod = ".".join(parts[:-1])
        else:
            mod = ".".join(parts)
        yield mod


def smoke_district(name: str) -> dict:
    d = DISTRICTS_DIR / name
    result = {"district": name, "pass": 0, "skip": [], "fail": []}
    for mod in _iter_district_modules(d):
        try:
            importlib.import_module(mod)
            result["pass"] += 1
        except BaseException as exc:  # noqa: BLE001 — smoke must catch everything
            optional = _is_optional_dep_error(exc)
            if optional:
                result["skip"].append((mod, optional))
            else:
                tb = "".join(traceback.format_exception_only(type(exc), exc)).strip()
                result["fail"].append((mod, tb))
    return result


def run() -> int:
    districts = sorted(
        p.name for p in DISTRICTS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("__")
    )
    total_fail = 0
    print("=" * 60)
    print(f"VECTOR district smoke — {len(districts)} districts")
    print("=" * 60)
    for name in districts:
        r = smoke_district(name)
        status = "FAIL" if r["fail"] else "OK"
        print(
            f"  [{status:>4}] {name:<22} "
            f"pass={r['pass']:<3} skip={len(r['skip']):<2} fail={len(r['fail'])}"
        )
        for mod, tb in r["fail"]:
            print(f"         ✗ {mod}: {tb}")
            total_fail += 1
    print("=" * 60)
    if total_fail:
        print(f"  {total_fail} module(s) FAILED to import")
        return 1
    print("  ALL DISTRICTS IMPORT CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(run())
