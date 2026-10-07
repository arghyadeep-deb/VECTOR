import sys
from pathlib import Path

import subprocess
from loguru import logger
from core.config import CONFIG


class PhoneController:
    """ADB bridge for Android ambient node.

    Read-only by default — write ops (send_keyevent/tap/swipe/type_text/
    launch_app/unlock) must be called only after permission_gateway approval
    (RED tier). F-7: write primitives now require a gateway-minted control
    token (PermissionGateway.grant_control) so a direct caller that imports
    PhoneController cannot bypass the gate.
    """

    def __init__(self):
        # F-7: capability-token gate for write primitives.
        self._control_action_types = (
            "instagram_post_via_phone", "youtube_upload_via_phone",
            "pc_click", "click_screen", "gui_task", "desktop_task", "vision_control",
            "pc_type", "launch_app", "play_music",
        )
        self._adb_path: str = CONFIG.get("control", {}).get("adb_path", "adb")
        # Resolve adb (2026-07-21): the scheduled-task environment often lacks
        # adb on PATH, so a bare "adb" silently fails. Fall back to the
        # platform-tools bundled next to the codebase.
        import shutil as _shutil
        from pathlib import Path as _Path
        if self._adb_path == "adb" and not _shutil.which("adb"):
            _local = _Path(__file__).resolve().parents[2].parent / "platform-tools" / "adb.exe"
            if _local.exists():
                self._adb_path = str(_local)
        self._device_id: str | None = CONFIG.get("control", {}).get("phone_device_id", None)
        self._connected: bool = False
        self._check_connection()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_adb(self, *args: str, timeout: int = 10) -> tuple[bool, str]:
        """Run an adb command, returning (success, stdout_or_error)."""
        try:
            device_flag = ["-s", self._device_id] if self._device_id else []
            cmd = [self._adb_path] + device_flag + list(args)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                err = (result.stderr or "").strip()
                logger.debug(f"[VECTOR][phone_controller] adb non-zero rc: {err}")
                return (False, err)
            return (True, output)
        except FileNotFoundError:
            logger.warning("[VECTOR][phone_controller] adb binary not found — phone control unavailable")
            return (False, "adb not found")
        except subprocess.TimeoutExpired:
            logger.warning("[VECTOR][phone_controller] adb command timed out")
            return (False, "timeout")
        except Exception as e:
            logger.error(f"[VECTOR][phone_controller] _run_adb error: {e}")
            return (False, str(e))

    def _verify_control_token(self, token, *allowed_action_types) -> bool:
        """F-7: verify a gateway-minted control token. Direct callers without a
        valid token are refused by the write primitives below."""
        try:
            from core.loop.permission_gateway import PermissionGateway
            gw = PermissionGateway()
        except Exception as _e:
            logger.warning(f"[VECTOR][phone_controller] gateway unavailable — control token check fails closed: {_e}")
            return False
        for _a in allowed_action_types:
            if gw.verify_control(token, _a):
                return True
        return False

    def _check_connection(self) -> bool:
        """Parse `adb devices` to determine if a device is attached."""
        try:
            ok, output = self._run_adb("devices", timeout=5)
            if not ok:
                self._connected = False
                logger.warning("[VECTOR][phone_controller] adb devices failed — phone not connected")
                return False

            # Format: header line + "<serial>\t<state>" lines
            lines = output.splitlines()
            devices = [
                line for line in lines[1:]
                if line.strip() and not line.startswith("*") and "\tdevice" in line
            ]
            self._connected = len(devices) > 0

            if self._connected:
                # Auto-fill device_id from first device if not configured
                if not self._device_id:
                    self._device_id = devices[0].split("\t")[0].strip()
                    logger.info(f"[VECTOR][phone_controller] auto-detected device: {self._device_id}")
                logger.info(f"[VECTOR][phone_controller] phone connected: {self._device_id}")
            else:
                logger.info("[VECTOR][phone_controller] no Android device connected")

            return self._connected
        except Exception as e:
            logger.error(f"[VECTOR][phone_controller] _check_connection error: {e}")
            self._connected = False
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        """Return current connection state (does not re-probe)."""
        return self._connected

    def get_notifications(self) -> list[dict]:
        """Read active notifications via dumpsys.

        Returns list of {package, title, text, time} dicts.
        Empty list if phone not connected or parse fails.
        """
        try:
            if not self._connected:
                return []

            ok, output = self._run_adb("shell", "dumpsys", "notification", "--noredact", timeout=15)
            if not ok or not output:
                return []

            notifications: list[dict] = []
            lines = output.splitlines()
            current: dict = {}

            for line in lines:
                stripped = line.strip()

                if "NotificationRecord(" in stripped:
                    if current:
                        notifications.append(current)
                    current = {"package": "", "title": "", "text": "", "time": ""}

                # Package name
                if stripped.startswith("pkg=") and current is not None:
                    current["package"] = stripped.split("pkg=", 1)[1].split()[0]

                # android.title
                if "android.title" in stripped and "=" in stripped and current is not None:
                    current["title"] = stripped.split("=", 1)[1].strip()

                # android.text
                if "android.text" in stripped and "=" in stripped and current is not None:
                    current["text"] = stripped.split("=", 1)[1].strip()

                # postTime
                if "postTime=" in stripped and current is not None:
                    current["time"] = stripped.split("postTime=", 1)[1].split()[0]

            if current:
                notifications.append(current)

            logger.debug(f"[VECTOR][phone_controller] got {len(notifications)} notifications")
            return notifications

        except Exception as e:
            logger.error(f"[VECTOR][phone_controller] get_notifications error: {e}")
            return []

    def take_screenshot(self, local_path: str = "./data/phone_screenshot.png") -> bool:
        """Capture phone screen and pull it to local_path.

        Flow: screencap → pull → rm remote file.
        Returns True on success, False on failure.
        """
        try:
            if not self._connected:
                logger.warning("[VECTOR][phone_controller] take_screenshot: phone not connected")
                return False

            # Ensure local directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)

            ok, _ = self._run_adb("shell", "screencap", "-p", "/sdcard/vector_screen.png", timeout=15)
            if not ok:
                logger.error("[VECTOR][phone_controller] screencap failed")
                return False

            ok, _ = self._run_adb("pull", "/sdcard/vector_screen.png", local_path, timeout=20)
            if not ok:
                logger.error("[VECTOR][phone_controller] adb pull failed")
                return False

            # Cleanup remote file (best-effort)
            self._run_adb("shell", "rm", "/sdcard/vector_screen.png", timeout=5)

            logger.info(f"[VECTOR][phone_controller] screenshot saved → {local_path}")
            return True

        except Exception as e:
            logger.error(f"[VECTOR][phone_controller] take_screenshot error: {e}")
            return False

    def get_sms_recent(self, count: int = 10) -> list[dict]:
        """Read recent SMS from inbox via content provider.

        Returns list of {from, body, timestamp}.
        """
        try:
            if not self._connected:
                return []

            ok, output = self._run_adb(
                "shell", "content", "query",
                "--uri", "content://sms/inbox",
                "--projection", "address:body:date",
                timeout=15,
            )
            if not ok or not output:
                return []

            messages: list[dict] = []
            for line in output.splitlines():
                line = line.strip()
                if not line.startswith("Row:"):
                    continue

                row: dict = {"from": "", "body": "", "timestamp": ""}
                parts = line.split(", ")
                for part in parts:
                    if part.startswith("address="):
                        row["from"] = part.split("=", 1)[1]
                    elif part.startswith("body="):
                        row["body"] = part.split("=", 1)[1]
                    elif part.startswith("date="):
                        row["timestamp"] = part.split("=", 1)[1]

                messages.append(row)
                if len(messages) >= count:
                    break

            logger.debug(f"[VECTOR][phone_controller] got {len(messages)} SMS")
            return messages

        except Exception as e:
            logger.error(f"[VECTOR][phone_controller] get_sms_recent error: {e}")
            return []

    def send_keyevent(self, keycode: int, *, control_token: str | None = None) -> bool:
        """Send an Android key event. F-7: requires a gateway control token."""
        if not self._verify_control_token(control_token, *self._control_action_types):
            logger.warning("[VECTOR][phone_controller] send_keyevent blocked — no valid control token")
            return False
        try:
            if not self._connected:
                logger.warning("[VECTOR][phone_controller] send_keyevent: phone not connected")
                return False

            ok, _ = self._run_adb("shell", "input", "keyevent", str(keycode), timeout=10)
            if ok:
                logger.info(f"[VECTOR][phone_controller] keyevent {keycode} sent")
            else:
                logger.error(f"[VECTOR][phone_controller] keyevent {keycode} failed")
            return ok

        except Exception as e:
            logger.error(f"[VECTOR][phone_controller] send_keyevent error: {e}")
            return False

    # ------------------------------------------------------------------
    # Interaction primitives — the app-automation layer (IG posting, WA replies).
    # F-7: all RED-tier writes require a gateway control token.
    # ------------------------------------------------------------------

    def tap(self, x: int, y: int, *, control_token: str | None = None) -> bool:
        """Tap screen coordinate (x, y). F-7: requires a gateway control token."""
        if not self._verify_control_token(control_token, *self._control_action_types):
            logger.warning("[VECTOR][phone_controller] tap blocked — no valid control token")
            return False
        if not self._connected:
            return False
        ok, _ = self._run_adb("shell", "input", "tap", str(int(x)), str(int(y)), timeout=10)
        logger.info(f"[VECTOR][phone_controller] tap ({x},{y}) {'ok' if ok else 'FAIL'}")
        return ok

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300,
              *, control_token: str | None = None) -> bool:
        """Swipe from (x1,y1) to (x2,y2) over duration_ms. F-7: requires a control token."""
        if not self._verify_control_token(control_token, *self._control_action_types):
            logger.warning("[VECTOR][phone_controller] swipe blocked — no valid control token")
            return False
        if not self._connected:
            return False
        ok, _ = self._run_adb(
            "shell", "input", "swipe",
            str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration_ms)),
            timeout=10,
        )
        logger.info(f"[VECTOR][phone_controller] swipe ({x1},{y1})->({x2},{y2}) {'ok' if ok else 'FAIL'}")
        return ok

    def type_text(self, text: str, *, control_token: str | None = None) -> bool:
        """Type text into the focused field. F-7: requires a gateway control token.
        ASCII/basic only — `input text` can't do emoji/newlines (Android limitation).
        ponytail: install ADBKeyboard IME later if captions need emoji/unicode."""
        if not self._verify_control_token(control_token, *self._control_action_types):
            logger.warning("[VECTOR][phone_controller] type_text blocked — no valid control token")
            return False
        if not self._connected:
            return False
        # `input text` can't represent newlines anyway (see docstring) -- strip them
        # rather than let them survive into the adb shell command line, where adb
        # joins "shell" args into one string executed by the device's /system/bin/sh,
        # and an embedded literal newline acts as a statement separator (command
        # injection), unlike the other shell metacharacters escaped below.
        import re
        text = re.sub(r"[\r\n]", "", text)
        # `input text` treats spaces specially: encode as %s, escape shell-risky chars.
        safe = text.replace(" ", "%s")
        for ch in ("&", "<", ">", "|", ";", "(", ")", "`", '"', "'"):
            safe = safe.replace(ch, "\\" + ch)
        ok, _ = self._run_adb("shell", "input", "text", safe, timeout=15)
        logger.info(f"[VECTOR][phone_controller] type_text ({len(text)} chars) {'ok' if ok else 'FAIL'}")
        return ok

    def launch_app(self, package: str, *, control_token: str | None = None) -> bool:
        """Launch an app by package name (e.g. com.instagram.android). F-7: requires a control token."""
        if not self._verify_control_token(control_token, *self._control_action_types):
            logger.warning("[VECTOR][phone_controller] launch_app blocked — no valid control token")
            return False
        if not self._connected:
            return False
        ok, _ = self._run_adb(
            "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1",
            timeout=15,
        )
        logger.info(f"[VECTOR][phone_controller] launch {package} {'ok' if ok else 'FAIL'}")
        return ok

    def current_app(self) -> str:
        """Return the foreground app's package name (best-effort, '' on failure).
        Used to verify launch_app actually landed on the target app."""
        if not self._connected:
            return ""
        ok, out = self._run_adb("shell", "dumpsys", "window", timeout=10)
        if not ok:
            return ""
        import re
        m = re.search(r"mCurrentFocus=Window\{[^}]*\s+([\w.]+)/", out)
        return m.group(1) if m else ""

    def unlock(self, *, control_token: str | None = None) -> bool:
        """Wake + swipe up to dismiss a no-PIN lock screen. F-7: requires a control token.
        (For PIN locks, the owner must set screen lock to None — VECTOR does not store a PIN.)"""
        if not self._verify_control_token(control_token, *self._control_action_types):
            logger.warning("[VECTOR][phone_controller] unlock blocked — no valid control token")
            return False
        if not self._connected:
            return False
        self.send_keyevent(224, control_token=control_token)  # KEYCODE_WAKEUP
        return self.swipe(360, 1200, 360, 300, 250, control_token=control_token)


# ----------------------------------------------------------------------
# Smoke test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    ctrl = PhoneController()

    connected = ctrl.is_connected()
    if not isinstance(connected, bool):
        logger.error("[VECTOR][phone_controller] is_connected() returned wrong type")
        ok = False
    else:
        logger.info(f"[VECTOR][phone_controller] is_connected: {connected}")

    notifs = ctrl.get_notifications()
    if not isinstance(notifs, list):
        logger.error("[VECTOR][phone_controller] get_notifications() returned wrong type")
        ok = False
    else:
        logger.info(f"[VECTOR][phone_controller] notifications: {len(notifs)} entries")

    print("✅ phone_controller OK" if ok else "❌ FAILED")
