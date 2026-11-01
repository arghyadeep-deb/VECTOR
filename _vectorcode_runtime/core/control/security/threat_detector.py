import os
import sys

__all__ = [
    "check_file_entropy",
    "check_process_anomalies",
    "scan_processes_inprocess",
]

from pathlib import Path

import math
from loguru import logger

from core.config import CONFIG

# ---------------------------------------------------------------------------
# Known suspicious process name fragments (lower-cased)
# ---------------------------------------------------------------------------
_SUSPICIOUS_NAMES: set[str] = {
    "cryptominer", "keylogger", "miner", "rat", "netcat",
    "mimikatz", "cobaltstrike", "metasploit", "ncrack",
    "xmrig", "monero", "cpuminer",
}

# Fragments this short appear inside ordinary words ("rat" in "WMIRegistrationService", "miner" in "determiner"), so
# they only count as a whole token of the process name ("rat.exe", "some-rat-client"), never as a substring. The
# substring match flagged a Lenovo/Windows WMI service and pushed the HUD's threat level to HIGH.
_TOKEN_ONLY_NAMES: frozenset[str] = frozenset({"rat", "miner"})


def _name_is_suspicious(name: str) -> str | None:
    """Return the matched fragment if this (lower-cased) process name looks malicious, else None."""
    import re

    tokens = {t for t in re.split(r"[^a-z0-9]+", name) if t}
    for bad in _SUSPICIOUS_NAMES:
        if bad in _TOKEN_ONLY_NAMES:
            if bad in tokens:
                return bad
        elif bad in name:
            return bad
    return None


# Temp / writable dirs that legitimate system processes should NOT live in
_SUSPICIOUS_DIRS: tuple[str, ...] = (
    "\\temp\\", "\\tmp\\", "\\appdata\\local\\temp\\",
    "/tmp/", "/var/tmp/",
)


_SNAPSHOT_SCRIPT = Path(__file__).resolve().parent / "process_snapshot.py"


def check_process_anomalies() -> list[dict]:
    """Scan running processes for suspicious indicators. Returns [{pid, name, exe, suspicious: bool, reason: str}].

    Runs in a CHILD process (2026-09-27): psutil's Windows process enumeration holds the GIL for seconds (constructing a
    `Process` for a protected pid falls back to a whole-system query; py-spy showed it as the API's main GIL consumer), so
    doing it in-process froze the API. Falls back to the in-process scan only if the child cannot be run.
    Never raises.
    """
    import json
    import subprocess

    try:
        out = subprocess.run(
            [sys.executable, str(_SNAPSHOT_SCRIPT), "anomalies"],
            capture_output=True, text=True, timeout=90, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        rows = json.loads(out)
        if isinstance(rows, list):
            return rows
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[VECTOR][threat_detector] child process scan failed ({e}); scanning in-process")
    return scan_processes_inprocess()


_SIGNATURE_CACHE: dict[tuple[str, int, int, int], bool] = {}


def _win_verify_trust(path: str) -> bool:
    """WinVerifyTrust (embedded Authenticode signature, no UI, no revocation/network lookup): True only for a valid signature.

    Native and fast (milliseconds); a PowerShell Get-AuthenticodeSignature took ~1.6 s idle and 15 s+ on a loaded machine.
    Catalog-signed system files report 'no signature' here, which is fine: installers carry embedded signatures.
    """
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class WINTRUST_FILE_INFO(ctypes.Structure):
        _fields_ = [("cbStruct", wintypes.DWORD), ("pcwszFilePath", wintypes.LPCWSTR), ("hFile", wintypes.HANDLE),
                    ("pgKnownSubject", ctypes.c_void_p)]

    class WINTRUST_DATA(ctypes.Structure):
        _fields_ = [("cbStruct", wintypes.DWORD), ("pPolicyCallbackData", ctypes.c_void_p), ("pSIPClientData", ctypes.c_void_p),
                    ("dwUIChoice", wintypes.DWORD), ("fdwRevocationChecks", wintypes.DWORD), ("dwUnionChoice", wintypes.DWORD),
                    ("pFile", ctypes.POINTER(WINTRUST_FILE_INFO)), ("dwStateAction", wintypes.DWORD),
                    ("hWVTStateData", wintypes.HANDLE), ("pwszURLReference", wintypes.LPCWSTR), ("dwProvFlags", wintypes.DWORD),
                    ("dwUIContext", wintypes.DWORD), ("pSignatureSettings", ctypes.c_void_p)]

    action = GUID(0x00AAC56B, 0xCD44, 0x11D0, (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE))
    file_info = WINTRUST_FILE_INFO(ctypes.sizeof(WINTRUST_FILE_INFO), path, None, None)
    data = WINTRUST_DATA()
    data.cbStruct = ctypes.sizeof(WINTRUST_DATA)
    data.dwUIChoice = 2                     # WTD_UI_NONE
    data.fdwRevocationChecks = 0            # WTD_REVOKE_NONE
    data.dwUnionChoice = 1                  # WTD_CHOICE_FILE
    data.pFile = ctypes.pointer(file_info)
    data.dwStateAction = 1                  # WTD_STATEACTION_VERIFY
    data.dwProvFlags = 0x1000               # WTD_CACHE_ONLY_URL_RETRIEVAL: never touch the network
    wintrust = ctypes.windll.wintrust
    wintrust.WinVerifyTrust.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), ctypes.c_void_p]
    wintrust.WinVerifyTrust.restype = ctypes.c_long
    invalid_hwnd = wintypes.HANDLE(-1)
    try:
        status = wintrust.WinVerifyTrust(invalid_hwnd, ctypes.byref(action), ctypes.byref(data))
    finally:
        data.dwStateAction = 2              # WTD_STATEACTION_CLOSE releases the provider state
        wintrust.WinVerifyTrust(invalid_hwnd, ctypes.byref(action), ctypes.byref(data))
    return status == 0


def _is_validly_signed(exe_path: str) -> bool:
    """True only when Windows verifies Authenticode, cached by path plus the file's current identity."""
    if sys.platform != "win32" or not exe_path:
        return False
    try:
        stat = os.stat(exe_path)
        key = (os.path.normcase(os.path.abspath(exe_path)), stat.st_size, stat.st_mtime_ns, getattr(stat, "st_ino", 0))
    except OSError:
        # Do not cache a missing/inaccessible path: an executable may appear or be replaced at that path moments later.
        return False
    if key in _SIGNATURE_CACHE:
        return _SIGNATURE_CACHE[key]
    try:
        ok = _win_verify_trust(exe_path)
    except Exception:  # noqa: BLE001 -- unknown means "not proven signed"
        ok = False
    _SIGNATURE_CACHE[key] = ok
    return ok


def scan_processes_inprocess() -> list[dict]:
    """The scan itself (what the child runs). Same result shape as check_process_anomalies(). Never raises."""
    results: list[dict] = []
    try:
        import psutil  # type: ignore
        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            try:
                info = proc.info
                pid: int = info.get("pid") or 0
                name: str = (info.get("name") or "").lower()
                exe: str = (info.get("exe") or "").lower()
                cmdline: list[str] = info.get("cmdline") or []

                suspicious = False
                reason = ""

                # Check name against known bad fragments
                bad = _name_is_suspicious(name)
                if bad:
                    suspicious = True
                    reason = f"suspicious name fragment: {bad}"

                # Check if exe lives in a temp directory. 2026-09-27: a validly Authenticode-signed executable there is an installer
                # or updater (the VS Code installer alone pushed the HUD's threat level to HIGH), not malware staging.
                if not suspicious and exe:
                    for bad_dir in _SUSPICIOUS_DIRS:
                        if bad_dir in exe:
                            if _is_validly_signed(info.get("exe") or exe):
                                reason = f"signed executable in temp dir (installer/updater): {exe}"
                            else:
                                suspicious = True
                                reason = f"executable in temp dir: {exe}"
                            break

                # Flag scripts launched by interpreters from temp dirs. Do not re-flag an already trusted signed installer merely
                # because argv[0] is its own temp path.
                interpreter = Path(name).stem in {"python", "pythonw", "node", "nodejs", "pwsh", "powershell", "wscript", "cscript"}
                if not suspicious and cmdline and interpreter:
                    for arg in cmdline[1:] if len(cmdline) > 1 else cmdline:
                        arg_lower = arg.lower()
                        for bad_dir in _SUSPICIOUS_DIRS:
                            if bad_dir in arg_lower:
                                suspicious = True
                                reason = f"cmdline arg references temp dir: {arg}"
                                break
                        if suspicious:
                            break

                results.append({
                    "pid": pid,
                    "name": info.get("name") or "",
                    "exe": info.get("exe") or "",
                    "suspicious": suspicious,
                    "reason": reason,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                logger.warning(f"[VECTOR][threat_detector] process scan partial error: {e}")
                continue

    except ImportError:
        logger.error("[VECTOR][threat_detector] psutil not installed — cannot scan processes")
    except Exception as e:
        logger.error(f"[VECTOR][threat_detector] check_process_anomalies error: {e}")

    logger.info(
        f"[VECTOR][threat_detector] scanned {len(results)} processes, "
        f"{sum(1 for r in results if r['suspicious'])} suspicious"
    )
    return results


def check_file_entropy(file_path: str) -> float:
    """Compute Shannon entropy (0–8) of a file's bytes.

    Entropy > 7.5 typically indicates encryption / packing → suspicious.
    Returns -1.0 on error.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"[VECTOR][threat_detector] file not found: {file_path}")
            return -1.0

        freq = [0] * 256
        total = 0
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                total += len(chunk)
                for b in chunk:
                    freq[b] += 1

        if total == 0:
            return 0.0

        entropy = 0.0
        for count in freq:
            if count:
                p = count / total
                entropy -= p * math.log2(p)

        logger.debug(f"[VECTOR][threat_detector] entropy({path.name}) = {entropy:.3f}")
        return round(entropy, 4)

    except Exception as e:
        logger.error(f"[VECTOR][threat_detector] check_file_entropy error: {e}")
        return -1.0


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    # --- check_process_anomalies ---
    procs = check_process_anomalies()
    if not isinstance(procs, list):
        logger.error("[VECTOR][threat_detector] check_process_anomalies did not return list")
        ok = False
    else:
        logger.info(f"[VECTOR][threat_detector] {len(procs)} processes returned")
        if procs:
            first = procs[0]
            for key in ("pid", "name", "exe", "suspicious", "reason"):
                if key not in first:
                    logger.error(f"[VECTOR][threat_detector] missing key '{key}' in process dict")
                    ok = False
                    break

    # --- check_file_entropy on a known file ---
    config_path = str(Path(__file__).parent.parent.parent.parent / "core" / "config.py")
    entropy = check_file_entropy(config_path)
    if not isinstance(entropy, float) or entropy < 0:
        logger.error(f"[VECTOR][threat_detector] bad entropy result: {entropy}")
        ok = False
    else:
        suspicious_flag = entropy > 7.5
        logger.info(
            f"[VECTOR][threat_detector] config.py entropy={entropy:.3f} "
            f"{'(SUSPICIOUS)' if suspicious_flag else '(clean)'}"
        )

    # --- entropy on non-existent file ---
    bad_entropy = check_file_entropy("/nonexistent/file.bin")
    if bad_entropy != -1.0:
        logger.error(f"[VECTOR][threat_detector] expected -1.0 for missing file, got {bad_entropy}")
        ok = False

    print("✅ threat_detector.py OK" if ok else "❌ FAILED")
