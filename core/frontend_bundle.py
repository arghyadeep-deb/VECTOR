"""Frontend bundle validation for development vs production VECTOR HUDs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


DEV_ONLY_SCRIPTS = frozenset({"js/demo.js"})


@dataclass(frozen=True)
class FrontendBundleCheck:
    status: str
    local_scripts: list[str]
    dev_only_scripts: list[str]
    message: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def extract_local_scripts(html: str) -> list[str]:
    scripts = re.findall(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", html, flags=re.I)
    return [
        src.replace("\\", "/")
        for src in scripts
        if not re.match(r"^[a-z][a-z0-9+.-]*:", src, flags=re.I)
        and not src.startswith("//")
    ]


def validate_frontend_bundle(
    html_path: str | Path,
    *,
    production: bool = False,
) -> FrontendBundleCheck:
    path = Path(html_path)
    html = path.read_text(encoding="utf-8")
    local_scripts = extract_local_scripts(html)
    dev_only = sorted(script for script in local_scripts if script in DEV_ONLY_SCRIPTS)

    if production and dev_only:
        return FrontendBundleCheck(
            status="fail",
            local_scripts=local_scripts,
            dev_only_scripts=dev_only,
            message="production bundle includes development-only scripts: "
            + ", ".join(dev_only),
        )

    return FrontendBundleCheck(
        status="ok",
        local_scripts=local_scripts,
        dev_only_scripts=dev_only,
        message="frontend bundle script boundary valid",
    )
