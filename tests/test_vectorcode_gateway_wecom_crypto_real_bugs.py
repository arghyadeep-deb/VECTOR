"""Regression for vectorcode/src/gateway/platforms/wecom_crypto.py -- the REAL,
live WXBizMsgCrypt class (imported by gateway/platforms/wecom_callback.py,
wired into the real WeCom callback server), not the dormant duplicate at
vectorcode/src/comms/wecom_crypto.py that already got its own fix+test this
cycle. This file had the identical two bugs:

1. decrypt()'s signature check used a plain `!=` instead of
   secrets.compare_digest() -- a timing side-channel on a crypto signature.
2. encrypt() built its XML response with whatever `ET` got bound by a
   defusedxml-vs-stdlib try/except -- defusedxml.ElementTree deliberately
   has no Element/SubElement/tostring builder API (confirmed live:
   hasattr(defusedxml.ElementTree, "Element") is False), so encrypt()
   raised AttributeError immediately whenever defusedxml is installed
   (confirmed installed in this environment). The guard itself was also
   pointless here: grep confirms ET.* is never used for parsing untrusted
   input anywhere in this file, only for building encrypt()'s own output.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from gateway.platforms.wecom_crypto import DecryptError, WXBizMsgCrypt, SignatureError, _sha1_signature

_TOKEN = "test_token_12345"
_AES_KEY = "a" * 43  # must be exactly 43 chars
_RECEIVE_ID = "ww1234567890abcdef"


def _crypt():
    return WXBizMsgCrypt(_TOKEN, _AES_KEY, _RECEIVE_ID)


def test_decrypt_rejects_wrong_signature():
    crypt = _crypt()
    try:
        crypt.decrypt("deadbeef" * 5, "1700000000", "nonce123", "notrealciphertext==")
        assert False, "expected SignatureError"
    except SignatureError:
        pass


def test_decrypt_uses_constant_time_compare_not_bare_noteq():
    import inspect
    src = inspect.getsource(WXBizMsgCrypt.decrypt)
    assert "secrets.compare_digest" in src
    assert "if expected != msg_signature" not in src


def test_encrypt_round_trips_through_decrypt():
    crypt = _crypt()
    envelope_xml = crypt.encrypt("hello from VECTOR")
    # Parse the envelope the same way a real WeCom server response is read.
    import re
    enc = re.search(r"<Encrypt>(.*?)</Encrypt>", envelope_xml).group(1)
    sig = re.search(r"<MsgSignature>(.*?)</MsgSignature>", envelope_xml).group(1)
    ts = re.search(r"<TimeStamp>(.*?)</TimeStamp>", envelope_xml).group(1)
    nonce = re.search(r"<Nonce>(.*?)</Nonce>", envelope_xml).group(1)
    plain = crypt.decrypt(sig, ts, nonce, enc)
    assert plain.decode("utf-8") == "hello from VECTOR"


def test_encrypt_works_even_with_defusedxml_installed():
    # This is the actual regression: encrypt() used to raise AttributeError
    # here whenever defusedxml was importable (confirmed installed in this
    # environment) because the bound `ET` had no Element/SubElement.
    import defusedxml.ElementTree as _dET
    assert not hasattr(_dET, "Element")  # confirms the hazard is real here
    crypt = _crypt()
    result = crypt.encrypt("still works")
    assert "<Encrypt>" in result and "<MsgSignature>" in result


def test_decrypt_rejects_noncanonical_base64_even_with_valid_signature():
    crypt = _crypt()
    malformed = "!!!!"
    signature = _sha1_signature(_TOKEN, "1700000000", "nonce123", malformed)
    with pytest.raises(DecryptError, match="invalid base64"):
        crypt.decrypt(signature, "1700000000", "nonce123", malformed)


def test_encoding_key_must_decode_to_exact_aes256_key():
    with pytest.raises(ValueError, match="valid base64"):
        WXBizMsgCrypt(_TOKEN, "!" * 43, _RECEIVE_ID)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
