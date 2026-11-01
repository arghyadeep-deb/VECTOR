"""Yuanbao protocol — message serialization/deserialization for WebSocket transport."""

import json
import struct
from typing import Any

def encode_message(msg_type: int, payload: dict, seq: int = 1) -> bytes:
    """Encode a Yuanbao protocol message."""
    body = json.dumps(payload).encode()
    header = struct.pack("!HHI", 1, msg_type, seq)
    return header + body

def decode_message(data: bytes) -> dict:
    """Decode a Yuanbao protocol message."""
    if len(data) < 8: return {"type": "unknown", "data": {}}
    version, cmd, seq = struct.unpack("!HHI", data[:8])
    body = data[8:]
    try:
        payload = json.loads(body.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    return {"version": version, "cmd": cmd, "seq": seq, "data": payload}
