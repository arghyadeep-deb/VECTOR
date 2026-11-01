# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

from __future__ import annotations

import sys
from pathlib import Path

SYSTEMD_TEMPLATE = """\
[Unit]
Description=VectorCode Gateway Daemon
After=network.target

[Service]
Type=simple
ExecStart={python} -m vector.daemon.gateway
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""

LAUNCHD_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vector.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>vector.daemon.gateway</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""

def generate_systemd_service(output: Path | None = None) -> str:
    content = SYSTEMD_TEMPLATE.format(python=sys.executable)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)
    return content

def generate_launchd_plist(output: Path | None = None) -> str:
    content = LAUNCHD_TEMPLATE.format(python=sys.executable)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)
    return content

class ServiceManager:
    """Thin object wrapper over this module's systemd/launchd generators.

    core/loop/autonomous_loop.py does
    `from vectorcode.src.daemon.service import ServiceManager` and
    `self._daemon_mgr = ServiceManager()` -- that class never existed in
    this file, so the import always raised ImportError, silently caught
    by autonomous_loop.py's bare except (self._daemon_mgr = None).  Wraps
    the two generator functions that already constitute this module's
    entire daemon-management capability; no new behavior invented.
    """

    def install_systemd(self, output: Path | None = None) -> str:
        return generate_systemd_service(output)

    def install_launchd(self, output: Path | None = None) -> str:
        return generate_launchd_plist(output)
