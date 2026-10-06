"""Regression for vectorcode/src/cli/scan_cmd.py:

The module did `from vectorcode.src.vector_cli.scan_cmd import *` (bringing
in the real PrivacyScanner, which has a run_all() -> list[ScanResult]
method) and then UNCONDITIONALLY defined its own `class PrivacyScanner`
below that import -- a stub with a scan(path) method and no run_all() at
all. Since the stub is defined at module level with no `except` guard, it
silently overwrote the real class every time this module was imported,
regardless of whether the wildcard import succeeded.

server/routes.py's GET /v1/security/scan endpoint does
`from vectorcode.src.cli.scan_cmd import PrivacyScanner; scanner.run_all()`
-- this crashed with AttributeError on every single call.
"""
from __future__ import annotations


def test_cli_scan_cmd_exports_the_real_privacy_scanner_with_run_all():
    from vectorcode.src.cli.scan_cmd import PrivacyScanner
    from vectorcode.src.vector_cli.scan_cmd import PrivacyScanner as RealPrivacyScanner

    assert PrivacyScanner is RealPrivacyScanner
    scanner = PrivacyScanner()
    assert hasattr(scanner, "run_all"), (
        "server/routes.py's /v1/security/scan endpoint calls run_all() -- "
        "a stub PrivacyScanner without it would crash every request"
    )


def test_security_scan_endpoint_does_not_crash_on_privacy_scanner():
    from vectorcode.src.cli.scan_cmd import PrivacyScanner

    scanner = PrivacyScanner()
    results = scanner.run_all()
    assert isinstance(results, list)
    for r in results:
        assert hasattr(r, "status")
        assert hasattr(r, "name")
