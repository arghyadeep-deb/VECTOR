"""WeCom callback verification — URL verification and event callback handling."""

import hashlib
import secrets
import struct
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
from typing import Optional

from loguru import logger

try:
    from Cryptodome.Cipher import AES
    import base64
    _CRYPTO = True
except ImportError:
    _CRYPTO = False

class WeComCallback:
    def __init__(self, token: str = "", encoding_aes_key: str = "", corp_id: str = ""):
        self.token = token
        self.encoding_aes_key = encoding_aes_key
        self.corp_id = corp_id

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echo_str: str) -> Optional[str]:
        """Verify the callback URL by decrypting echo_str."""
        if not _CRYPTO: return None
        sort_str = "".join(sorted([self.token, timestamp, nonce, echo_str]))
        calc_sig = hashlib.sha1(sort_str.encode()).hexdigest()  # nosec — WeCom API mandates SHA1
        # Timing-unsafe comparison on a crypto signature -- same bug class
        # already fixed in the sibling wecom_crypto.py this cycle.
        if not secrets.compare_digest(calc_sig, msg_signature): return None
        try:
            key = base64.b64decode(self.encoding_aes_key + "=", validate=True)
            cipher = AES.new(key, AES.MODE_CBC, key[:16])
            decrypted = cipher.decrypt(base64.b64decode(echo_str))
            pad = decrypted[-1]
            if pad < 1 or pad > 32 or decrypted[-pad:] != bytes([pad]) * pad:
                return None
            content = decrypted[:-pad][16:]
            if len(content) < 4:
                return None
            message_length = struct.unpack("!I", content[:4])[0]
            if message_length > len(content) - 4:
                return None
            message = content[4:4 + message_length]
            receive_id = content[4 + message_length:].decode("utf-8")
            if not secrets.compare_digest(receive_id, self.corp_id):
                return None
            return message.decode("utf-8")
        except Exception as e:
            logger.warning(f"Decrypt failed: {e}")
            return None

    def parse_callback_xml(self, xml_data: str) -> dict:
        """Parse WeCom callback XML message."""
        root = ET.fromstring(xml_data)
        return {child.tag: child.text for child in root}
