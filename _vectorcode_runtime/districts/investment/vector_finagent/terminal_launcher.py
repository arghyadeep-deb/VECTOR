"""
VECTOR Financial Terminal Launcher
Manages the C++/Qt6 native financial terminal binary.

The terminal is a separate high-performance native binary built from
core/fincept/qt/ using CMake + Qt6. It handles:
  - Real-time charting and data visualization (native C++, no browser)
  - 16 broker integrations (Zerodha, IBKR, Alpaca, Angel One, etc.)
  - Crypto exchange WebSocket (HyperLiquid, Kraken)
  - Visual workflow node editor
  - Embedded Python analytics via Python/C API

VECTOR's Python agents feed analysis results to the terminal;
the terminal handles real-time rendering and order execution.

Build (one-time, requires Qt 6.8.3 + MSVC/GCC/Clang):
    cmake --preset win-release   (Windows)
    cmake --preset linux-release (Linux)
    cmake --preset macos-release (macOS)

Usage:
    launcher = FinAgentTerminalLauncher()
    launcher.ensure_built()
    launcher.launch()
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from loguru import logger

_QT_DIR  = Path(__file__).parent / "qt"
_BIN_DIR = _QT_DIR / "build"

_PLATFORM_PRESET = {
    "win32":  "win-release",
    "linux":  "linux-release",
    "darwin": "macos-release",
}
_PLATFORM_BINARY = {
    "win32":  "FinceptTerminal.exe",
    "linux":  "FinceptTerminal",
    "darwin": "FinceptTerminal",
}

# Fallback search order for pre-built binaries (MinGW build, VECTOR user dir)
_WIN_BINARY_FALLBACKS = [
    Path("C:/fincept-build/win-mingw/FinceptTerminal.exe"),
    Path.home() / ".vector" / "fincept" / "FinceptTerminal.exe",
]
# Qt DLLs dir for MinGW build — needed in PATH when launching
_WIN_QT_MINGW_BIN = Path("C:/Qt/6.8.3/mingw_64/bin")


class FinAgentTerminalLauncher:
    """Manages the C++/Qt6 VECTOR Financial Terminal binary."""

    def __init__(self) -> None:
        self._platform = sys.platform if sys.platform in _PLATFORM_PRESET else "linux"
        self._preset   = _PLATFORM_PRESET[self._platform]
        self._bin_name = _PLATFORM_BINARY[self._platform]
        self._bin_path = _BIN_DIR / self._preset / self._bin_name
        self._proc: subprocess.Popen | None = None

    @property
    def is_built(self) -> bool:
        if self._bin_path.exists():
            return True
        if self._platform == "win32":
            return any(p.exists() for p in _WIN_BINARY_FALLBACKS)
        return False

    def _resolved_bin_path(self) -> Path:
        """Return the first existing binary path (canonical > fallbacks)."""
        if self._bin_path.exists():
            return self._bin_path
        if self._platform == "win32":
            for p in _WIN_BINARY_FALLBACKS:
                if p.exists():
                    return p
        return self._bin_path

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def cmake_source_present(self) -> bool:
        return (_QT_DIR / "CMakeLists.txt").exists()

    async def build(self, parallel: int | None = None) -> bool:
        """Build the C++ terminal from source. Requires Qt 6.8.3 installed."""
        if not self.cmake_source_present():
            logger.error("[VECTOR][terminal] CMakeLists.txt not found at {}", _QT_DIR)
            return False

        logger.info("[VECTOR][terminal] configuring CMake preset={}", self._preset)
        loop = asyncio.get_event_loop()

        def _run_cmake():
            # Configure
            configure = subprocess.run(
                ["cmake", "--preset", self._preset],
                cwd=str(_QT_DIR),
                capture_output=True, text=True,
            )
            if configure.returncode != 0:
                logger.error("[VECTOR][terminal] cmake configure failed:\n{}", configure.stderr[:500])
                return False

            # Build
            build_args = ["cmake", "--build", "--preset", self._preset]
            if parallel:
                build_args += ["--parallel", str(parallel)]
            build = subprocess.run(
                build_args,
                cwd=str(_QT_DIR),
                capture_output=False,  # show progress
            )
            return build.returncode == 0

        success = await loop.run_in_executor(None, _run_cmake)
        if success:
            logger.info("[VECTOR][terminal] build complete → {}", self._bin_path)
        return success

    async def ensure_built(self, auto_build: bool = False) -> bool:
        """Ensure the binary exists. Optionally trigger build if missing."""
        if self.is_built:
            return True
        if auto_build:
            logger.info("[VECTOR][terminal] binary not found, building...")
            return await self.build()
        logger.warning(
            "[VECTOR][terminal] binary not found. Build with:\n"
            "  cd core/fincept/qt && cmake --preset {} && cmake --build --preset {}",
            self._preset, self._preset
        )
        return False

    def launch(self, detached: bool = True) -> bool:
        """Launch the terminal binary. Returns True if started."""
        if not self.is_built:
            logger.error("[VECTOR][terminal] binary not found: {}", self._bin_path)
            return False
        if self.is_running:
            logger.info("[VECTOR][terminal] already running (PID={})", self._proc.pid)
            return True

        bin_path = self._resolved_bin_path()
        logger.info("[VECTOR][terminal] launching {}", bin_path)
        try:
            env = os.environ.copy()
            # Ensure Qt MinGW DLLs are in PATH when running the MinGW build
            if self._platform == "win32" and _WIN_QT_MINGW_BIN.exists():
                env["PATH"] = str(_WIN_QT_MINGW_BIN) + os.pathsep + env.get("PATH", "")
            self._proc = subprocess.Popen(
                [str(bin_path)],
                cwd=str(bin_path.parent),
                start_new_session=detached,
                env=env,
            )
            logger.info("[VECTOR][terminal] launched PID={}", self._proc.pid)
            return True
        except Exception as e:
            logger.debug("[VECTOR][terminal_launcher] caught Exception: %s", e)
            logger.error("[VECTOR][terminal] launch failed: {}", e)
            return False

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc = None
            logger.info("[VECTOR][terminal] stopped")

    def status(self) -> dict:
        return {
            "cmake_source": self.cmake_source_present(),
            "binary_built": self.is_built,
            "binary_path":  str(self._bin_path),
            "running":      self.is_running,
            "platform":     self._platform,
            "preset":       self._preset,
        }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    launcher = FinAgentTerminalLauncher()
    st = launcher.status()
    print("OK terminal_launcher.py — VECTOR Financial Terminal Launcher")
    print(f"  platform: {st['platform']}  preset: {st['preset']}")
    print(f"  cmake source: {st['cmake_source']}")
    print(f"  binary built: {st['binary_built']}")
    print(f"  binary path: {st['binary_path']}")
    if not st["binary_built"]:
        print(f"  Build: cd core/fincept/qt && cmake --preset {st['preset']}")
