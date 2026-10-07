import sys

__all__ = [
    "check_port_open",
    "get_dns_servers",
    "get_local_ip",
]

from pathlib import Path

import socket
from loguru import logger

from core.config import CONFIG


def get_local_ip() -> str:
    """Return the primary local IP address of this machine.

    Uses a UDP trick (no data sent) to discover which interface routes
    to the outside world. Returns '127.0.0.1' on failure.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Connect to an external IP (doesn't actually send anything)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        logger.debug(f"[VECTOR][node_router] local IP = {ip}")
        return ip
    except Exception as e:
        logger.warning(f"[VECTOR][node_router] get_local_ip fallback: {e}")
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception as e2:
            logger.error(f"[VECTOR][node_router] get_local_ip total failure: {e2}")
            return "127.0.0.1"


def check_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if TCP port is accepting connections on *host*.

    Never raises — returns False on any error.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout) as _:
            logger.debug(f"[VECTOR][node_router] {host}:{port} is OPEN")
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        logger.debug(f"[VECTOR][node_router] {host}:{port} is CLOSED or unreachable")
        return False
    except Exception as e:
        logger.warning(f"[VECTOR][node_router] check_port_open({host},{port}) error: {e}")
        return False


def get_dns_servers() -> list[str]:
    """Return a list of DNS server IPs configured on this machine.

    Strategy (platform-aware, graceful fallback):
      1. Windows: parse ``ipconfig /all`` for "DNS Servers" lines.
      2. Unix/Linux/Mac: parse ``/etc/resolv.conf`` for nameserver lines.
      3. Fallback: return empty list (never raises).
    """
    servers: list[str] = []
    try:
        import platform
        if platform.system() == "Windows":
            import subprocess
            result = subprocess.run(
                ["ipconfig", "/all"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if "DNS Servers" in stripped or (servers and stripped and stripped[0].isdigit()):
                    # "   DNS Servers . . . . . : 192.168.1.1"
                    # continuation lines (indented with only an IP)
                    if ":" in stripped:
                        ip_part = stripped.split(":")[-1].strip()
                        _add_ips(ip_part, servers)
                    elif stripped and stripped[0].isdigit():
                        _add_ips(stripped, servers)
        else:
            resolv = Path("/etc/resolv.conf")
            if resolv.exists():
                for line in resolv.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            _add_ips(parts[1], servers)

    except Exception as e:
        logger.warning(f"[VECTOR][node_router] get_dns_servers error: {e}")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in servers:
        if s not in seen:
            seen.add(s)
            unique.append(s)

    logger.info(f"[VECTOR][node_router] DNS servers: {unique}")
    return unique


def _add_ips(text: str, target: list[str]) -> None:
    """Parse space/comma-separated IPs from *text* and append valid ones to *target*."""
    for part in text.replace(",", " ").split():
        part = part.strip()
        if part:
            try:
                socket.inet_pton(socket.AF_INET, part)
                target.append(part)
            except OSError:
                try:
                    socket.inet_pton(socket.AF_INET6, part)
                    target.append(part)
                except OSError:
                    logger.opt(exception=True).warning(
                        f"[VECTOR][node_router] _add_ips: {part!r} is neither a valid IPv4 nor IPv6 address"
                    )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    # --- get_local_ip ---
    ip = get_local_ip()
    if not isinstance(ip, str) or not ip:
        logger.error(f"[VECTOR][node_router] get_local_ip returned: {ip!r}")
        ok = False
    else:
        logger.info(f"[VECTOR][node_router] local IP = {ip}")

    # --- check_port_open (Ollama, likely running) ---
    ollama_open = check_port_open("127.0.0.1", 11434)
    logger.info(f"[VECTOR][node_router] Ollama port 11434 open = {ollama_open}")
    if not isinstance(ollama_open, bool):
        ok = False

    # Closed port must return False without raising
    closed = check_port_open("127.0.0.1", 19999)
    if closed is not False:
        logger.error(f"[VECTOR][node_router] expected False for closed port, got {closed}")
        ok = False

    # --- get_dns_servers ---
    dns = get_dns_servers()
    if not isinstance(dns, list):
        logger.error(f"[VECTOR][node_router] get_dns_servers returned: {dns!r}")
        ok = False
    else:
        logger.info(f"[VECTOR][node_router] DNS servers = {dns}")

    print("✅ node_router.py OK" if ok else "âŒ FAILED")
