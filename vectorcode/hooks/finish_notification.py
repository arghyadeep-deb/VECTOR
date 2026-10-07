# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/finish_notification.py

#!/usr/bin/env python3
"""
VECTOR Finish Notification Hook — Stop
Windows toast notification when VECTOR finishes a task.
Adapted from article's macOS osascript — works on Windows 10/11.
"""
from loguru import logger
import subprocess
import sys

TITLE = "VECTOR · VectorCode"
MESSAGE = "Task complete — check the terminal."

# Method 1: Windows balloon tip via PowerShell (works without admin)
PS_SCRIPT = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.BalloonTipTitle = '{TITLE}'
$n.BalloonTipText = '{MESSAGE}'
$n.Visible = $true
$n.ShowBalloonTip(6000)
Start-Sleep -Milliseconds 6500
$n.Dispose()
"""

try:
    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", PS_SCRIPT],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
except Exception:
    # Method 2: Fallback — msg command (always available on Windows)
    try:
        subprocess.Popen(
            ["msg", "*", f"{TITLE}: {MESSAGE}"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        logger.opt(exception=True).debug("[VECTOR] suppressed exception")

sys.exit(0)
