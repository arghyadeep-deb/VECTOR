from __future__ import annotations

__all__ = [
    "get_sandbox",
    "SandboxConfig",
    "SandboxResult",
    "VectorSandbox",
]

import asyncio, os, subprocess, sys, tempfile, time
from dataclasses import dataclass, field
from loguru import logger

@dataclass
class SandboxConfig:
    timeout_secs: float = 30.0
    max_output_bytes: int = 1_048_576
    work_dir: str | None = None
    env_passthrough: list[str] = field(default_factory=list)
    python_executable: str = field(default_factory=lambda: sys.executable)
    max_memory_mb: int = 256
    SAFE_ENV_VARS: list[str] = field(default_factory=lambda: [
        "PATH","PYTHONPATH","HOME","USERPROFILE","TEMP","TMP",
        "LANG","LC_ALL","SYSTEMROOT","SystemRoot",
    ])

@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    elapsed_secs: float
    timed_out: bool = False
    truncated: bool = False

    @property
    def output(self) -> str:
        return self.stdout.strip() or self.stderr.strip()

class VectorSandbox:
    """Runs code/commands in a subprocess with a timeout, output cap, and a
    scrubbed environment -- NOT a real security sandbox. On POSIX, RLIMIT_AS/
    RLIMIT_CPU cap memory/CPU (best-effort; silently skipped on any error).
    On win32 (VECTOR's actual deployment platform) there is no resource
    limiting, filesystem confinement, or network isolation at all: _run()
    takes the Windows branch straight to a bare subprocess.Popen.

    This IS live, not just a theoretical risk if wired up later:
    core/loop/permission_gateway.py's RED-tier "execute_code" action handler
    runs real caller-supplied code through this exact class (get_sandbox() ->
    run_code_safe()/run_shell()) after council/owner approval -- the approval
    gate bounds WHO can trigger it, but once approved the code runs with full
    filesystem/network/environment access the main VECTOR process itself
    has, no real isolation beyond the scrubbed env + timeout. A real
    container-based sandbox already exists in this same package
    (core/sandbox/runner.py's ContainerRunner -- network=none, read-only
    mounts, mount allowlist) but execute_code does not use it. FLAG-FOR-OWNER
    (Phase 3 audit, 2026-10-01): switching execute_code to ContainerRunner
    when a container runtime is available, or adding real OS-level isolation
    for the Windows fallback, needs an explicit decision -- not a narrow
    same-session patch.

    Separately, districts/coding/coding_tools.py::run_code_safely() is also
    documented to run untrusted/LLM-generated code through this class but
    has zero real callers anywhere in the repo today (confirmed via grep) --
    dormant, not currently live, but would inherit this same gap the moment
    anything calls it."""
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()

    async def run_python(self, code: str, timeout: float | None = None, extra_env: dict | None = None) -> SandboxResult:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code); script = f.name
        try:
            return await self._run([self._config.python_executable, script], timeout or self._config.timeout_secs, extra_env)
        finally:
            try: os.unlink(script)
            except OSError: pass

    async def run_shell(self, command: str, timeout: float | None = None, extra_env: dict | None = None) -> SandboxResult:
        cmd = ["cmd.exe","/c",command] if sys.platform=="win32" else ["/bin/sh","-c",command]
        return await self._run(cmd, timeout or self._config.timeout_secs, extra_env)

    async def run_file(self, path: str, args: list[str] | None = None, timeout: float | None = None, extra_env: dict | None = None) -> SandboxResult:
        return await self._run([self._config.python_executable, path] + (args or []), timeout or self._config.timeout_secs, extra_env)

    async def run_code_safe(self, code: str, timeout: float | None = None) -> SandboxResult:
        parts = ["import sys, traceback", "try:"]
        for ln in code.splitlines():
            parts.append("    " + ln)
        parts += ["except Exception as _e:", "    print(type(_e).__name__, str(_e), file=sys.stderr)", "    sys.exit(1)"]
        joined = chr(10).join(parts)
        return await self.run_python(joined, timeout=timeout)

    async def _run(self, cmd: list[str], timeout: float, extra_env: dict | None) -> SandboxResult:
        env = self._build_env(extra_env)
        work_dir = self._config.work_dir or tempfile.mkdtemp(prefix="vector_sandbox_")
        if sys.platform == "win32":
            return await asyncio.to_thread(self._run_subprocess_sync, cmd, timeout, env, work_dir)
        preexec = None
        if sys.platform != "win32" and self._config.max_memory_mb > 0:
            mb = self._config.max_memory_mb * 1024 * 1024
            def _limits():
                try:
                    import resource
                    resource.setrlimit(resource.RLIMIT_AS, (mb, mb))
                    resource.setrlimit(resource.RLIMIT_CPU, (int(timeout)+5, int(timeout)+10))
                except Exception as e:
                    from loguru import logger
                    logger.debug("[VECTOR][sandbox] resource limit setup skipped: {}", e)
            preexec = _limits
        t0 = time.monotonic(); timed_out = False
        try:
            kw = {"preexec_fn": preexec} if preexec else {}
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=env, cwd=work_dir, **kw)
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                timed_out = True; proc.kill(); await proc.communicate(); out, err = b"", b"TIMEOUT"
        except Exception as e:
            return SandboxResult(False, "", str(e), -1, time.monotonic()-t0)
        elapsed = time.monotonic()-t0
        stdout = out.decode(errors="replace"); stderr = err.decode(errors="replace")
        truncated = False
        max_b = self._config.max_output_bytes
        if len(stdout)+len(stderr) > max_b:
            truncated = True
            stdout = stdout[:max_b//2]
            stderr = stderr[:max_b//2] + "TRUNCATED"
        exit_code = proc.returncode if not timed_out else -1
        logger.debug("[VECTOR][sandbox] exit={} elapsed={:.2f}s", exit_code, elapsed)
        return SandboxResult(exit_code==0 and not timed_out, stdout, stderr, exit_code, elapsed, timed_out, truncated)

    def _run_subprocess_sync(self, cmd: list[str], timeout: float, env: dict, work_dir: str) -> SandboxResult:
        t0 = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=work_dir,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                stdout, stderr = proc.communicate()
                stderr = (stderr or "") + "TIMEOUT"
        except Exception as e:
            return SandboxResult(False, "", str(e), -1, time.monotonic() - t0)

        truncated = False
        max_b = self._config.max_output_bytes
        if len(stdout) + len(stderr) > max_b:
            truncated = True
            stdout = stdout[:max_b // 2]
            stderr = stderr[:max_b // 2] + "TRUNCATED"
        exit_code = -1 if timed_out else proc.returncode
        elapsed = time.monotonic() - t0
        logger.debug("[VECTOR][sandbox] exit={} elapsed={:.2f}s", exit_code, elapsed)
        return SandboxResult(exit_code == 0 and not timed_out, stdout, stderr, exit_code, elapsed, timed_out, truncated)

    def _build_env(self, extra: dict | None) -> dict:
        env: dict[str,str] = {}
        for k in self._config.SAFE_ENV_VARS + self._config.env_passthrough:
            v = os.environ.get(k)
            if v: env[k] = v
        if extra: env.update(extra)
        return env

_sandbox: VectorSandbox | None = None
def get_sandbox(config: SandboxConfig | None = None) -> VectorSandbox:
    global _sandbox
    if _sandbox is None: _sandbox = VectorSandbox(config)
    return _sandbox
