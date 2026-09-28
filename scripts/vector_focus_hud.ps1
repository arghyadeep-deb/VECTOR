# Focus an already-open VECTOR HUD window.
#   exit 0 = an existing HUD was found (caller must NOT launch another one)
#   exit 1 = no HUD open (caller should launch one)
#
# -Deliberate : a real user action (the desktop icon) — always restore + bring
#               to the foreground. WITHOUT it (the wake-word _summon_hud path),
#               an already-visible HUD is left exactly where it is and focus is
#               NOT stolen — the wake word false-fires ~every 25s on ambient
#               noise, and yanking the HUD in front of whatever you're doing
#               that often is its own annoyance. A minimized HUD is still
#               restored either way.
param([switch]$Deliberate)
#
# Owner rule (2026-07-17): one system = ONE HUD.
#
# Detection enumerates ALL top-level windows in C# (EnumWindows), NOT
# `Get-Process chrome | Where MainWindowTitle`. Chrome runs the `--app` HUD
# windows under a process whose OWN .MainWindowTitle is usually empty/another
# window, so the Get-Process approach found nothing and every caller (desktop
# icon AND the wake-word _summon_hud) launched a DUPLICATE. That stacked 8-9
# "VECTOR" HUD windows: the wake word false-fired on ambient noise,
# _summon_hud "couldn't find" the existing HUD, and opened a new one each time
# (2026-07-17: 1 -> 4 windows in 40s idle). The window-finding loop lives in
# C# because a PowerShell EnumWindows delegate can't reliably write script scope.

$ErrorActionPreference = 'SilentlyContinue'

$src = @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class VecHud {
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern int GetWindowTextLength(IntPtr h);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindowAsync(IntPtr h, int c);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    static IntPtr found = IntPtr.Zero;
    static bool Visit(IntPtr h, IntPtr l) {
        if (found != IntPtr.Zero) return true;
        if (!IsWindowVisible(h)) return true;
        int len = GetWindowTextLength(h);
        if (len <= 0) return true;
        var sb = new StringBuilder(len + 1);
        GetWindowText(h, sb, sb.Capacity);
        // Exact title match so we never grab an editor / terminal that merely
        // mentions VECTOR.
        if (sb.ToString() == "VECTOR") { found = h; return false; }
        return true;
    }
    // deliberate=true (desktop icon): always restore + bring to foreground.
    // deliberate=false (wake-word summon): do NOTHING to a HUD that already
    // exists — return true only so the caller knows not to launch a duplicate.
    //   * If the owner MINIMIZED it, that's intentional; the wake word false-
    //     fires ~12x/5min on ambient noise, and un-minimizing it on every false
    //     wake made the HUD pop back open again and again right after the owner
    //     minimized it (2026-07-17 owner: "why does it open again n again when
    //     i minimise it"). Minimizing now STICKS — only the desktop icon
    //     (deliberate) brings it back. Voice conversation works headless anyway.
    //   * If it's visible, don't steal focus from whatever the owner is doing.
    public static bool FocusHud(bool deliberate) {
        found = IntPtr.Zero;
        EnumWindows(Visit, IntPtr.Zero);
        if (found == IntPtr.Zero) return false;
        if (deliberate) {
            ShowWindowAsync(found, IsIconic(found) ? 9 : 5);   // 9=RESTORE, 5=SHOW
            SetForegroundWindow(found);
        }
        // non-deliberate: found it, leave it exactly as-is (minimized stays
        // minimized, visible stays put). Just report "exists" so no duplicate.
        return true;
    }
}
'@
Add-Type -TypeDefinition $src -Language CSharp | Out-Null

if ([VecHud]::FocusHud([bool]$Deliberate)) {
    Write-Output 'focused existing HUD'
    exit 0
}
exit 1
