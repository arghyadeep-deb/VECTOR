# VECTOR module -- ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb

"""GPU Docker container orchestration -- reusable for sandboxed agents.

Extracted from VectorCode's Pearl mining subsystem. The ``PearlDockerLauncher``
manages the full lifecycle of a GPU-enabled Docker container: image acquisition
(pull or build), launch with NVIDIA device passthrough, stop, health checks,
and log retrieval.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mining.stubs import MiningConfig

from core.mining.constants import (
    PEARL_CACHE_DIR,
    PEARL_IMAGE_TAG,
    PEARL_PINNED_REF,
    PEARL_REPO,
)

CONTAINER_NAME = "vector-pearl-miner"
LOCAL_MODEL_BIND_PATH = "/models/vector-local-pearl-model"

_SECRET_LOG_PATTERNS = (
    (re.compile(r"(rpc_password:\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(PEARLD_RPC_PASSWORD=)\S+"), r"\1[REDACTED]"),
    (re.compile(r'("PEARLD_RPC_PASSWORD"\s*:\s*")[^"]+(")'), r"\1[REDACTED]\2"),
)

class ImageAcquisitionError(RuntimeError):
    """Raised when an image can be neither found, pulled, nor built."""

class ConfigurationError(RuntimeError):
    """Raised when required env vars or config fields are missing."""

class ImageNotFound(Exception):
    """Fallback image-not-found error when Docker SDK is not installed."""

class NotFound(Exception):
    """Fallback Docker not-found error when Docker SDK is not installed."""

class APIError(Exception):
    """Fallback Docker API error when Docker SDK is not installed."""

def _docker_error_types() -> tuple[type[Exception], type[Exception], type[Exception]]:
    try:
        import docker.errors as derr
        return derr.ImageNotFound, derr.NotFound, derr.APIError
    except ImportError:
        return ImageNotFound, NotFound, APIError

class PearlDockerLauncher:
    """Orchestrate a GPU-enabled Docker container.

    Construct with a ``docker.DockerClient`` (real or mocked).
    """

    def __init__(self, client: Any):
        self._client = client
        self._container: Any | None = None

    # -----------------------------------------------------------------
    # Image acquisition
    # -----------------------------------------------------------------

    def ensure_image(self, tag: str) -> str:
        """Resolve ``tag`` to a usable local image, building if necessary.

        Selection order:
        1. Image present locally -> use it.
        2. Image pullable from a registry -> pull and use.
        3. ``tag`` matches VECTOR's default -> clone Pearl + ``docker build``.
        4. Otherwise -> ``ImageAcquisitionError``.
        """
        image_not_found, not_found, api_error = _docker_error_types()

        try:
            self._client.images.get(tag)
            return tag
        except image_not_found:
            pass

        pull_error: str | None = None
        try:
            self._client.images.pull(tag)
            return tag
        except (not_found, api_error) as exc:
            msg = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            pull_error = msg

        if tag == PEARL_IMAGE_TAG:
            cache = self._clone_pearl_repo()
            return self._docker_build(cache, tag)

        raise ImageAcquisitionError(
            f"image {tag!r} not present locally, not pullable, and not VECTOR's "
            f"default tag (no build fallback). Pull error: {pull_error}."
        )

    def _clone_pearl_repo(self) -> Path:
        PEARL_CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
        if PEARL_CACHE_DIR.exists() and (PEARL_CACHE_DIR / ".git").exists():
            self._git("fetch", "origin", cwd=PEARL_CACHE_DIR)
            try:
                self._git("checkout", "--detach", PEARL_PINNED_REF, cwd=PEARL_CACHE_DIR)
            except ImageAcquisitionError:
                self._git("checkout", "--detach", f"origin/{PEARL_PINNED_REF}", cwd=PEARL_CACHE_DIR)
            self._git("submodule", "update", "--init", "--recursive", cwd=PEARL_CACHE_DIR)
            self._git("clean", "-fdx", cwd=PEARL_CACHE_DIR)
        else:
            self._git("clone", "--branch", PEARL_PINNED_REF, PEARL_REPO, str(PEARL_CACHE_DIR), cwd=None)
            self._git("submodule", "update", "--init", "--recursive", cwd=PEARL_CACHE_DIR)
        return PEARL_CACHE_DIR

    def _docker_build(self, repo_path: Path, tag: str) -> str:
        self._patch_vllm_dockerfile(repo_path)
        self._patch_vllm_entrypoint(repo_path)
        cmd = [
            "docker", "buildx", "build",
            "--ulimit", "nofile=1048576:1048576",
            "-t", tag,
            "-f", "miner/vllm-miner/Dockerfile",
            ".",
        ]
        try:
            subprocess.run(cmd, cwd=str(repo_path), check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr_tail = (exc.stderr or "").strip().splitlines()[-10:]
            raise ImageAcquisitionError(
                f"docker build failed (exit {exc.returncode}): " + " | ".join(stderr_tail)
            ) from exc
        return tag

    def _patch_vllm_dockerfile(self, repo_path: Path) -> None:
        dockerfile = repo_path / "miner" / "vllm-miner" / "Dockerfile"
        if not dockerfile.exists():
            return
        text = dockerfile.read_text()
        old = "FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu24.04"
        new = "FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04"
        if old in text:
            dockerfile.write_text(text.replace(old, new))

    def _patch_vllm_entrypoint(self, repo_path: Path) -> None:
        entrypoint = repo_path / "miner" / "vllm-miner" / "entrypoint.sh"
        if not entrypoint.exists():
            return
        text = entrypoint.read_text()
        old = (
            "# Wait until the gateway is ready\n"
            "curl -s http://localhost:8339/metrics --retry-delay 1 --retry 20 "
            "--retry-all-errors > /dev/null"
        )
        new = (
            "# Wait until the gateway is ready\n"
            "for i in $(seq 1 20); do\n"
            "    [ -S /tmp/pearlgw.sock ] && break\n"
            "    sleep 1\n"
            "done\n"
            "[ -S /tmp/pearlgw.sock ]"
        )
        if old in text:
            entrypoint.write_text(text.replace(old, new))

    # -----------------------------------------------------------------
    # Container lifecycle
    # -----------------------------------------------------------------

    def start(self, config: "MiningConfig", image: str) -> Any:
        """Launch the GPU miner container.

        ``image`` must already be resolved by ``ensure_image()``.
        Returns the docker.models.containers.Container object.
        """
        extra = config.extra
        password_env = extra.get("pearld_rpc_password_env", "PEARLD_RPC_PASSWORD")
        password = os.environ.get(password_env)
        if password is None:
            raise ConfigurationError(f"environment variable {password_env!r} is not set")

        hf_token_env = extra.get("hf_token_env", "HF_TOKEN")
        hf_token = os.environ.get(hf_token_env, "")

        model = str(extra.get("model", "pearl-ai/Llama-3.3-70B-Instruct-pearl"))
        local_model_path = extra.get("local_model_path")
        vllm_port = int(extra.get("vllm_port", 8000))
        gpu_mem = float(extra.get("gpu_memory_utilization", 0.96))
        max_len = int(extra.get("max_model_len", 8192))

        model_arg = model
        local_model_host_path: Path | None = None
        if local_model_path:
            local_model_host_path = Path(str(local_model_path)).expanduser().resolve()
            if not local_model_host_path.exists():
                raise ConfigurationError(f"local model path does not exist: {local_model_host_path}")
            if not local_model_host_path.is_dir():
                raise ConfigurationError("local model path must be a directory")
            model_arg = LOCAL_MODEL_BIND_PATH

        command = [
            model_arg, "--host", "0.0.0.0", "--port", str(vllm_port),
            "--gpu-memory-utilization", str(gpu_mem),
            "--enforce-eager", "--max-model-len", str(max_len),
        ]
        if local_model_host_path is not None:
            command.extend(["--served-model-name", model])
        command.extend(_extra_vllm_args(extra.get("vllm_args", [])))

        environment = {
            "PEARLD_RPC_URL": extra.get("pearld_rpc_url", "http://localhost:44107"),
            "PEARLD_RPC_USER": extra.get("pearld_rpc_user", "rpcuser"),
            "PEARLD_RPC_PASSWORD": password,
            "PEARLD_MINING_ADDRESS": config.wallet_address,
            "HF_TOKEN": hf_token,
            "MINER_RPC_TRANSPORT": "uds",
            "MINER_RPC_SOCKET_PATH": "/tmp/pearlgw.sock",
        }

        cuda_devices = str(extra.get("cuda_visible_devices", "")).strip()
        device_ids = [part.strip() for part in cuda_devices.split(",") if part.strip()]
        if device_ids:
            environment["CUDA_VISIBLE_DEVICES"] = ",".join(str(idx) for idx, _ in enumerate(device_ids))
            environment["NVIDIA_VISIBLE_DEVICES"] = ",".join(device_ids)

        try:
            from docker.types import DeviceRequest
            if device_ids:
                device_requests = [DeviceRequest(device_ids=device_ids, capabilities=[["gpu"]])]
            else:
                device_requests = [DeviceRequest(count=-1, capabilities=[["gpu"]])]
        except ImportError:
            device_requests = None

        hf_cache = Path.home() / ".cache" / "huggingface"
        volumes = {str(hf_cache): {"bind": "/root/.cache/huggingface", "mode": "rw"}}
        if local_model_host_path is not None:
            volumes[str(local_model_host_path)] = {"bind": LOCAL_MODEL_BIND_PATH, "mode": "ro"}

        try:
            self._container = self._client.containers.run(
                image=image, command=command,
                name=CONTAINER_NAME, detach=True, auto_remove=False,
                restart_policy={"Name": "unless-stopped"},
                device_requests=device_requests,
                shm_size="8g", network_mode="host",
                volumes=volumes, environment=environment,
            )
        except Exception as exc:
            cls = exc.__class__.__name__
            raise ConfigurationError(
                f"failed to launch container from image {image!r} ({cls}); "
                f"check `docker ps -a` and `docker logs {CONTAINER_NAME}`"
            ) from None
        return self._container

    def _current_container(self) -> Any | None:
        if self._container is not None:
            return self._container
        _, not_found, _ = _docker_error_types()
        try:
            self._container = self._client.containers.get(CONTAINER_NAME)
        except not_found:
            return None
        except Exception:
            return None
        return self._container

    def stop(self, timeout: int = 30) -> None:
        container = self._current_container()
        if container is None:
            return
        try:
            container.stop(timeout=timeout)
        except Exception:
            pass
        try:
            container.remove()
        except Exception:
            pass
        self._container = None

    def is_running(self) -> bool:
        container = self._current_container()
        if container is None:
            return False
        try:
            container.reload()
        except Exception:
            return False
        return getattr(container, "status", "") == "running"

    def get_logs(self, tail: int = 200) -> str:
        container = self._current_container()
        if container is None:
            return ""
        raw = container.logs(tail=tail)
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = str(raw)
        return _redact_container_logs(text)

    @staticmethod
    def _git(*args: str, cwd: Path | None) -> None:
        cmd = ["git", *args]
        try:
            subprocess.run(cmd, cwd=str(cwd) if cwd is not None else None, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr_tail = (exc.stderr or "").strip().splitlines()[-5:]
            raise ImageAcquisitionError(
                f"`{' '.join(cmd)}` failed (exit {exc.returncode}): " + " | ".join(stderr_tail)
            ) from exc

def _redact_container_logs(text: str) -> str:
    redacted = text
    for pattern, replacement in _SECRET_LOG_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted

def _extra_vllm_args(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return shlex.split(value)
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    raise ConfigurationError("[mining.extra].vllm_args must be a string or list")
