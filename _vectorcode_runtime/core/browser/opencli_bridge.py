"""
OpenCLI bridge — wraps @jackwener/opencli TypeScript npm tool via subprocess.
Converts any website to a CLI interface usable by VECTOR's research district.
"""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import asyncio
import json
from loguru import logger


class OpenCLIBridge:
    """
    Subprocess bridge to @jackwener/opencli npm tool.
    Usage: install with `npm install -g @jackwener/opencli`
    """

    async def is_available(self) -> bool:
        """Check if opencli is installed globally."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "@jackwener/opencli", "--version",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def get_site_interface(self, site: str) -> dict:
        """
        Get CLI interface definition for a website.
        Returns dict with available commands and parameters.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "-y", "@jackwener/opencli", "describe", site,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode == 0:
                try:
                    return {"status": "ok", "site": site, "interface": json.loads(stdout.decode())}
                except json.JSONDecodeError:
                    return {"status": "ok", "site": site, "interface": stdout.decode()[:2000]}
            return {"status": "error", "error": stderr.decode()[:200]}
        except asyncio.TimeoutError:
            return {"status": "error", "error": "opencli timed out"}
        except FileNotFoundError:
            return {"status": "error", "error": "npx not installed"}
        except Exception as e:
            logger.warning("[VECTOR][opencli] error: {}", e)
            return {"status": "error", "error": str(e)}

    async def run_command(self, site: str, command: str, args: dict = None) -> dict:
        """Run a CLI command on a website via opencli."""
        cmd_args = ["npx", "-y", "@jackwener/opencli", "run", site, command]
        if args:
            cmd_args += [f"--{k}={v}" for k, v in args.items()]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            return {
                "status": "ok" if proc.returncode == 0 else "error",
                "output": stdout.decode()[:5000],
                "error": stderr.decode()[:500] if proc.returncode != 0 else None,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    async def test():
        bridge = OpenCLIBridge()
        available = await bridge.is_available()
        print(f"OpenCLI available: {available}")
        print("✅ opencli_bridge OK")
    asyncio.run(test())
