"""Regression: WXBizMsgCrypt.decrypt() compared the computed WeCom
callback signature against the caller-supplied one with a plain string
`!=` instead of a constant-time comparison -- a timing side-channel on a
cryptographic signature check, same bug class already fixed in
core/api/routers/websocket.py's require_auth_handshake() this cycle.
Fixed with secrets.compare_digest().
"""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.comms.wecom_crypto import WXBizMsgCrypt, SignatureError


def _make_crypt():
    # encoding_aes_key must decode (with "=" appended) to a 32-byte AES key.
    aes_key = base64.b64encode(b"0" * 32).decode().rstrip("=")
    assert len(aes_key) == 43
    return WXBizMsgCrypt(token="mytoken", encoding_aes_key=aes_key, receive_id="corp123")


def test_wrong_signature_is_rejected():
    crypt = _make_crypt()
    xml = crypt.encrypt("hello")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    encrypt = root.find("Encrypt").text
    timestamp = root.find("TimeStamp").text
    nonce = root.find("Nonce").text

    try:
        crypt.decrypt("0" * 40, timestamp, nonce, encrypt)
        assert False, "expected SignatureError"
    except SignatureError:
        pass


def test_correct_signature_round_trips():
    crypt = _make_crypt()
    xml = crypt.encrypt("hello world")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    encrypt = root.find("Encrypt").text
    sig = root.find("MsgSignature").text
    timestamp = root.find("TimeStamp").text
    nonce = root.find("Nonce").text

    decrypted = crypt.decrypt(sig, timestamp, nonce, encrypt)
    assert decrypted.decode() == "hello world"


def test_decrypt_uses_constant_time_compare():
    """Source-level guard: the signature check must go through
    secrets.compare_digest(), not a plain != comparison."""
    import inspect
    from vectorcode.src.comms import wecom_crypto
    src = inspect.getsource(wecom_crypto.WXBizMsgCrypt.decrypt)
    assert "compare_digest" in src
    assert "!= msg_signature" not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
