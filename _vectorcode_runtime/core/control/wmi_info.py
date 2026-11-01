"""Real WMI (Windows Management Instrumentation) queries — owner capability
sweep, 2026-10-25 ("do this except outlook": PowerPoint + WMI).

Read-only hardware/software inventory, deliberately GREEN tier (no gate
needed — nothing here mutates anything). Deeper than psutil's own
CPU/memory/disk/battery snapshot (core/control/pc_controller.py's
get_system_stats): BIOS, motherboard, GPU, and installed-software list.

installed_software() deliberately does NOT use WMI's own Win32_Product
class -- that class is documented to trigger an MSI "repair"/reconfigure
pass as a side effect of simply enumerating it (real, well-known Windows
behaviour, not a theoretical risk), which is never acceptable for a
read-only info query. Uses the registry's own Uninstall key instead
(the same place Control Panel's "Programs and Features" reads from) --
same data, zero side effects.
"""
import json
import subprocess
import sys
import winreg

from loguru import logger

__all__ = ["hardware_info", "installed_software"]


# Runs in a brand-new, throwaway Python process every call -- see
# hardware_info()'s docstring for why. Deliberately self-contained (only
# stdlib + `wmi`/`json`, no VECTOR imports) since it runs outside this
# process entirely.
_HARDWARE_QUERY_SCRIPT = r"""
import json
try:
    import wmi
    c = wmi.WMI()
    cpu = c.Win32_Processor()[0] if c.Win32_Processor() else None
    bios = c.Win32_BIOS()[0] if c.Win32_BIOS() else None
    system = c.Win32_ComputerSystem()[0] if c.Win32_ComputerSystem() else None
    gpus = [g.Name for g in c.Win32_VideoController()] if c.Win32_VideoController() else []
    disks = [{"model": d.Model, "size_gb": round(int(d.Size) / (1024**3), 1) if d.Size else None}
             for d in c.Win32_DiskDrive()] if c.Win32_DiskDrive() else []
    print(json.dumps({
        "cpu": cpu.Name.strip() if cpu and cpu.Name else "unknown",
        "manufacturer": system.Manufacturer if system else "unknown",
        "model": system.Model if system else "unknown",
        "bios_version": bios.SMBIOSBIOSVersion if bios else "unknown",
        "ram_gb": round(int(system.TotalPhysicalMemory) / (1024**3), 1) if system and system.TotalPhysicalMemory else None,
        "gpus": gpus,
        "disks": disks,
    }))
except Exception as e:
    print(json.dumps({"error": str(e)}))
"""


def hardware_info() -> dict:
    """CPU, BIOS, motherboard, GPU(s), RAM, disk(s) — real WMI query.

    2026-10-25: FOUR prior in-process fix attempts (documented in git
    history for this file) all failed live with COM error -2147221020
    "Invalid syntax" in the FastAPI server's shared long-lived thread,
    despite every one working perfectly in a plain isolated script --
    including two different COM-apartment-model variants and a
    teardown/no-teardown variant that was verified clean in isolation but
    STILL failed live, meaning the real cause is something about that
    specific shared thread's accumulated COM state across many OTHER COM
    calls over the server's lifetime (Office automation, pywinauto
    notifications) that isn't fully reproducible outside it. A fifth
    attempt bypassing the `wmi` package for a lower-level COM API
    (SWbemLocator) SEGFAULTED the live interpreter outright.
    Architectural fix instead of another COM-state guess: run the query in
    a genuinely fresh, throwaway Python subprocess every time. A new
    process always gets pristine COM state -- exactly matching the
    plain-script case that always worked -- so this sidesteps the shared-
    thread contamination entirely rather than trying to out-guess it, and
    even a hard crash in that subprocess can never take down VECTOR itself
    (unlike the SWbemLocator attempt, which crashed the live server).
    Costs real subprocess-spawn latency (observed ~0.3-0.6s) in exchange
    for actually being reliable.
    """
    if sys.platform != "win32":
        return {"error": "hardware_info is Windows-only"}
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", _HARDWARE_QUERY_SCRIPT],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()[-300:]
            logger.error(f"[VECTOR][wmi] hardware_info subprocess exit {proc.returncode}: {err}")
            return {"error": f"hardware_info subprocess failed: {err or 'no stderr'}"}
        return json.loads((proc.stdout or "").strip() or "{}")
    except subprocess.TimeoutExpired:
        logger.error("[VECTOR][wmi] hardware_info subprocess timed out")
        return {"error": "hardware_info timed out"}
    except json.JSONDecodeError as e:
        logger.error(f"[VECTOR][wmi] hardware_info subprocess returned invalid JSON: {e}")
        return {"error": f"hardware_info returned invalid JSON: {e}"}
    except Exception as e:
        logger.error(f"[VECTOR][wmi] hardware_info error: {e}")
        return {"error": str(e)}


def installed_software(limit: int = 50) -> dict:
    """List installed programs via the registry's Uninstall key (same
    source as Control Panel's "Programs and Features") -- never
    Win32_Product, which has a real, documented MSI-repair side effect."""
    if sys.platform != "win32":
        return {"programs": [], "error": "installed_software is Windows-only"}
    programs: list[dict] = []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    try:
        for hive, subkey in roots:
            try:
                key = winreg.OpenKey(hive, subkey)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub_name = winreg.EnumKey(key, i)
                    sub = winreg.OpenKey(key, sub_name)
                    name, _ = winreg.QueryValueEx(sub, "DisplayName")
                    try:
                        version, _ = winreg.QueryValueEx(sub, "DisplayVersion")
                    except OSError:
                        version = ""
                    if name:
                        programs.append({"name": name, "version": version})
                except OSError:
                    continue
        programs.sort(key=lambda p: p["name"].lower())
        # dedupe (32-bit/64-bit views often list the same program twice)
        seen = set()
        deduped = []
        for p in programs:
            if p["name"] not in seen:
                seen.add(p["name"])
                deduped.append(p)
        return {"programs": deduped[:limit], "total": len(deduped)}
    except Exception as e:
        logger.error(f"[VECTOR][wmi] installed_software error: {e}")
        return {"programs": [], "error": str(e)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    hw = hardware_info()
    sw = installed_software(limit=5)
    ok = "error" not in hw and "error" not in sw and sw.get("total", 0) > 0
    print("✅ wmi_info OK" if ok else f"❌ FAILED: hw={hw} sw={sw}")
