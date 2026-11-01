from __future__ import annotations

__all__ = [
    "get_sandbox",
    "SandboxConfig",
    "SandboxResult",
    "VectorSandbox",
]

import asyncio, os, shutil, subprocess, sys, tempfile, time
from dataclasses import dataclass, field
from functools import lru_cache
from loguru import logger

from core.sandbox.runner import ContainerRunner


_CONTAINER_IMAGE = "vector-sandbox:latest"
_container_runtime_name: str | None = None
_container_unavailable_reason = "container availability has not been checked"
_fallback_warning_emitted = False


@lru_cache(maxsize=1)
def _container_runtime_status() -> tuple[str | None, str]:
    """Return an available runtime name and a human-readable status.

    Detection is cached because probing an image invokes the runtime CLI. All
    failures are converted to an unavailable status so sandbox callers never
    fail merely because Docker or Podman is unhealthy.
    """
    found_runtime = False
    failure_reasons: list[str] = []
    for runtime in ("docker", "podman"):
        try:
            executable = shutil.which(runtime)
            if executable is None:
                continue
            found_runtime = True
            inspected = subprocess.run(
                [executable, "image", "inspect", _CONTAINER_IMAGE],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if inspected.returncode == 0:
                return runtime, f"{runtime} and {_CONTAINER_IMAGE} are available"

            detail = (inspected.stderr or inspected.stdout or "").strip().lower()
            if "permission denied" in detail or "access is denied" in detail:
                failure_reasons.append(f"{runtime} access was denied")
            elif "daemon" in detail or "cannot connect" in detail:
                failure_reasons.append(f"{runtime} daemon is unavailable")
            else:
                failure_reasons.append(
                    f"{_CONTAINER_IMAGE} was not found locally via {runtime}"
                )
        except Exception as exc:
            failure_reasons.append(f"{runtime} probe failed: {type(exc).__name__}")

    if not found_runtime:
        return None, "Docker/Podman runtime binary was not found"
    return None, "; ".join(failure_reasons) or "container runtime probe failed"


def _container_runtime_available() -> bool:
    """Check once whether a supported runtime and sandbox image are usable."""
    global _container_runtime_name, _container_unavailable_reason
    runtime, reason = _container_runtime_status()
    _container_runtime_name = runtime
    _container_unavailable_reason = reason
    return runtime is not None


def _warn_about_subprocess_fallback() -> None:
    """Log the weaker isolation warning once per process."""
    global _fallback_warning_emitted
    if _fallback_warning_emitted:
        return
    _fallback_warning_emitted = True
    logger.warning(
        "[VECTOR][sandbox] RED-tier/sandboxed code is executing without "
        "container isolation: {}. Falling back to the local subprocess sandbox.",
        _container_unavailable_reason,
    )

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
    """Runs code/commands in an isolated container when one is available.

    Docker or Podman execution uses ``vector-sandbox:latest`` through
    :class:`ContainerRunner`: the container has no network, receives one
    scrubbed JSON request on stdin, and returns one sentinel-wrapped JSON
    result on stdout. No host paths are mounted for code or shell execution.

    If neither a supported runtime nor the image is available, execution
    falls back to the original local subprocess implementation with a
    one-time warning. That fallback has a scrubbed environment, timeout, and
    output cap; POSIX also gets best-effort RLIMIT_AS/RLIMIT_CPU limits. It is
    not a real security boundary. In particular, the win32 fallback has no
    resource limiting, filesystem confinement, or network isolation.

    This IS live, not just a theoretical risk if wired up later:
    core/loop/permission_gateway.py's RED-tier "execute_code" action handler
    runs real caller-supplied code through this exact class (get_sandbox() ->
    run_code_safe()/run_shell()) after council/owner approval -- the approval
    gate bounds WHO can trigger it, but once approved the code runs with full
    filesystem/network/environment access the main VECTOR process itself
    has. OD-59 now routes self-contained Python and shell commands through
    ContainerRunner when possible; only the explicitly warned fallback keeps
    the weaker behavior.

    Separately, districts/coding/coding_tools.py::run_code_safely() is also
    documented to run untrusted/LLM-generated code through this class but
    has zero real callers anywhere in the repo today (confirmed via grep) --
    dormant, not currently live, but would inherit this same gap the moment
    anything calls it."""
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()

    async def run_python(self, code: str, timeout: float | None = None, extra_env: dict | None = None) -> SandboxResult:
        effective_timeout = timeout or self._config.timeout_secs
        if _container_runtime_available():
            return await self._run(["python3", "-c", code], effective_timeout, extra_env)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code); script = f.name
        try:
            return await self._run([self._config.python_executable, script], effective_timeout, extra_env)
        finally:
            try: os.unlink(script)
            except OSError: pass

    async def run_shell(self, command: str, timeout: float | None = None, extra_env: dict | None = None) -> SandboxResult:
        if _container_runtime_available():
            cmd = ["/bin/sh", "-c", command]
        else:
            cmd = ["cmd.exe","/c",command] if sys.platform=="win32" else ["/bin/sh","-c",command]
        return await self._run(cmd, timeout or self._config.timeout_secs, extra_env)

    async def run_file(self, path: str, args: list[str] | None = None, timeout: float | None = None, extra_env: dict | None = None) -> SandboxResult:
        # ContainerRunner's default mount allowlist has no roots. Keep file
        # execution on the host until an explicit, reviewed allowlist exists;
        # silently mounting the containing directory would weaken isolation.
        return await self._run(
            [self._config.python_executable, path] + (args or []),
            timeout or self._config.timeout_secs,
            extra_env,
            allow_container=False,
        )

    async def run_code_safe(self, code: str, timeout: float | None = None) -> SandboxResult:
        parts = ["import sys, traceback", "try:"]
        for ln in code.splitlines():
            parts.append("    " + ln)
        parts += ["except Exception as _e:", "    print(type(_e).__name__, str(_e), file=sys.stderr)", "    sys.exit(1)"]
        joined = chr(10).join(parts)
        return await self.run_python(joined, timeout=timeout)

    async def _run(
        self,
        cmd: list[str],
        timeout: float,
        extra_env: dict | None,
        *,
        allow_container: bool = True,
    ) -> SandboxResult:
        if allow_container and _container_runtime_available():
            return await self._run_container(cmd, timeout, dict(extra_env or {}))
        if allow_container:
            _warn_about_subprocess_fallback()
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

    async def _run_container(
        self,
        cmd: list[str],
        timeout: float,
        env: dict[str, str],
    ) -> SandboxResult:
        """Execute *cmd* through ContainerRunner and normalize its result."""
        started = time.monotonic()
        try:
            runner = ContainerRunner(
                timeout=int(timeout),
                runtime=_container_runtime_name or "docker",
            )
            raw = await asyncio.to_thread(
                runner.run,
                {"cmd": cmd, "timeout": timeout},
                mounts=None,
                env=env,
            )
        except Exception as exc:
            logger.opt(exception=True).error(
                "[VECTOR][sandbox] container execution failed: {}",
                exc,
            )
            return SandboxResult(False, "", str(exc), -1, time.monotonic() - started)

        if raw.get("error") or "success" not in raw:
            error_type = str(raw.get("error_type", ""))
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(raw.get("content", "Container execution failed")),
                exit_code=-1,
                elapsed_secs=time.monotonic() - started,
                timed_out=error_type == "timeout",
                truncated=False,
            )

        return SandboxResult(
            success=bool(raw.get("success", False)),
            stdout=str(raw.get("stdout", "")),
            stderr=str(raw.get("stderr", "")),
            exit_code=int(raw.get("exit_code", -1)),
            elapsed_secs=float(raw.get("elapsed_secs", time.monotonic() - started)),
            timed_out=bool(raw.get("timed_out", False)),
            truncated=bool(raw.get("truncated", False)),
        )

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
