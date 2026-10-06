from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from vector_cli import auth


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_spotify_callback_rejects_forged_state_and_keeps_waiting() -> None:
    port = _free_local_port()
    redirect_uri = f"http://127.0.0.1:{port}/spotify/callback"
    outcome: dict[str, object] = {}

    def wait_for_callback() -> None:
        outcome["result"] = auth._spotify_wait_for_callback(
            redirect_uri,
            expected_state="trusted-state",
            timeout_seconds=5.0,
        )

    waiter = threading.Thread(target=wait_for_callback)
    waiter.start()
    try:
        deadline = time.monotonic() + 2.0
        while True:
            try:
                urlopen(
                    f"{redirect_uri}?code=forged&state=attacker-state",
                    timeout=1.0,
                )
            except HTTPError as exc:
                assert exc.code == 400
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)

        assert waiter.is_alive(), "a forged callback must not terminate the OAuth wait"

        with urlopen(
            f"{redirect_uri}?code=legitimate&state=trusted-state",
            timeout=1.0,
        ) as response:
            assert response.status == 200
    finally:
        waiter.join(timeout=6.0)

    assert not waiter.is_alive()
    assert outcome["result"] == {
        "code": "legitimate",
        "state": "trusted-state",
        "error": None,
        "error_description": None,
    }
