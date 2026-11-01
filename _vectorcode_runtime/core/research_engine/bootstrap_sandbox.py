"""Bootstrap sandbox — Docker sandbox lifecycle for experiment execution."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


class BootstrapSandbox:
    def __init__(self, docker_image: str = "vector-experiment-runner:latest"):
        self.docker_image = docker_image
        self._docker_available: Optional[bool] = None
        self._image_built: bool = False

    def check_docker(self) -> bool:
        if self._docker_available is not None:
            return self._docker_available
        docker_path = shutil.which("docker")
        if docker_path is None:
            logger.info("Docker not found on PATH — sandbox unavailable")
            self._docker_available = False
            return False
        try:
            result = subprocess.run(
                [docker_path, "info"],
                capture_output=True, text=True, timeout=10,
            )
            self._docker_available = result.returncode == 0
            if not self._docker_available:
                logger.info("Docker daemon not running — falling back to subprocess")
            return self._docker_available
        except Exception as exc:
            logger.warning("Docker check failed: {}", exc)
            self._docker_available = False
            return False

    def build_image(self, dockerfile_dir: Optional[Path] = None) -> bool:
        if not self.check_docker():
            logger.warning("Cannot build image — Docker unavailable")
            return False
        df_dir = dockerfile_dir or Path(__file__).parent / "docker"
        df_path = df_dir / "Dockerfile"
        if not df_path.exists():
            logger.warning("No Dockerfile found at {}", df_path)
            return False
        try:
            logger.info("Building Docker image '{}' from {}", self.docker_image, df_dir)
            result = subprocess.run(
                ["docker", "build", "-t", self.docker_image, "."],
                capture_output=True, text=True, timeout=300, cwd=str(df_dir),
            )
            if result.returncode == 0:
                self._image_built = True
                logger.info("Docker image '{}' built successfully", self.docker_image)
            else:
                logger.error("Docker build failed: {}", result.stderr)
            return self._image_built
        except subprocess.TimeoutExpired:
            logger.warning("Docker build timed out after 300s")
            return False
        except Exception as exc:
            logger.error("Docker build error: {}", exc)
            return False

    def verify_sandbox(self) -> dict:
        if not self.check_docker():
            return {"ready": False, "backend": "subprocess", "message": "Docker unavailable — experiments will run via subprocess"}
        if not self._image_built:
            ok = self.build_image()
            if not ok:
                return {"ready": False, "backend": "subprocess", "message": "Image build failed — experiments will run via subprocess"}
        try:
            result = subprocess.run(
                ["docker", "run", "--rm", self.docker_image, "python", "-c", "print('sandbox_ok')"],
                capture_output=True, text=True, timeout=30,
            )
            ready = "sandbox_ok" in result.stdout
            return {
                "ready": ready,
                "backend": "docker",
                "message": "Sandbox verified OK" if ready else f"Sandbox check failed: {result.stderr}",
            }
        except Exception as exc:
            return {"ready": False, "backend": "subprocess", "message": f"Sandbox verify error: {exc}"}

    def get_status(self) -> dict:
        docker_ok = self.check_docker()
        return {
            "docker_available": docker_ok,
            "image_built": self._image_built,
            "backend": "docker" if (docker_ok and self._image_built) else "subprocess",
            "image": self.docker_image,
            "suggestion": "Install Docker Desktop or rely on subprocess fallback" if not docker_ok else None,
        }
