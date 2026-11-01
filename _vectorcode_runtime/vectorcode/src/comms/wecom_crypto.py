"""WeCom BizMsgCrypt — AES-CBC encryption for callback mode."""

import base64
import hashlib
import os
import secrets
import socket
import struct
from typing import Optional
try:
    from defusedxml import ElementTree as ET
except ImportError:
    from xml.etree import ElementTree as ET

# defusedxml.ElementTree deliberately exposes only parsing functions
# (fromstring/parse/XML) -- it has no Element/SubElement/tostring builder
# API, by design (its whole purpose is guarding untrusted-input parsing,
# not building output). encrypt() below only ever builds a response from
# VECTOR's own trusted data, never parses untrusted input, so it needs
# the real builder regardless of which ET got bound above -- using the
# defusedxml alias here raised AttributeError on every encrypt() call
# whenever defusedxml was installed (the preferred/common case).
from xml.etree import ElementTree as _ET_BUILD

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

class WeComCryptoError(Exception): pass
class SignatureError(WeComCryptoError): pass
class DecryptError(WeComCryptoError): pass
class EncryptError(WeComCryptoError): pass

class PKCS7Encoder:
    block_size = 32
    @classmethod
    def encode(cls, text: bytes) -> bytes:
        pad = cls.block_size - (len(text) % cls.block_size) or cls.block_size
        return text + bytes([pad]) * pad
    @classmethod
    def decode(cls, decrypted: bytes) -> bytes:
        if not decrypted: raise DecryptError("empty")
        pad = decrypted[-1]
        if pad < 1 or pad > cls.block_size: raise DecryptError("invalid padding")
        if decrypted[-pad:] != bytes([pad]) * pad: raise DecryptError("malformed padding")
        return decrypted[:-pad]

class WXBizMsgCrypt:
    def __init__(self, token: str, encoding_aes_key: str, receive_id: str):
        if len(encoding_aes_key) != 43: raise ValueError("encoding_aes_key must be 43 chars")
        self.token, self.receive_id = token, receive_id
        self.key = base64.b64decode(encoding_aes_key + "=")
        self.iv = self.key[:16]

    def decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> bytes:
        parts = sorted([self.token, timestamp, nonce, encrypt])
        expected = hashlib.sha1("".join(parts).encode()).hexdigest()  # nosec — WeCom API mandates SHA1
        if not secrets.compare_digest(expected, msg_signature):
            raise SignatureError("signature mismatch")
        try:
            cipher_text = base64.b64decode(encrypt, validate=True)
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded = decryptor.update(cipher_text) + decryptor.finalize()
            plain = PKCS7Encoder.decode(padded)[16:]
            if len(plain) < 4:
                raise DecryptError("truncated payload")
            xml_len = struct.unpack("!I", plain[:4])[0]
        except DecryptError:
            raise
        except Exception as exc:
            raise DecryptError(f"decrypt failed: {exc}") from exc
        if xml_len > len(plain) - 4:
            raise DecryptError("invalid message length")
        xml = plain[4:4 + xml_len]
        try:
            rid = plain[4 + xml_len:].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DecryptError("invalid receive_id encoding") from exc
        if rid != self.receive_id: raise DecryptError("receive_id mismatch")
        return xml

    def encrypt(self, plaintext: str, nonce: Optional[str] = None, timestamp: Optional[str] = None) -> str:
        nonce = nonce or ''.join(secrets.choice("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(10))
        timestamp = timestamp or str(int(__import__("time").time()))
        random_prefix = os.urandom(16)
        payload = random_prefix + struct.pack("!I", len(plaintext.encode("utf-8"))) + plaintext.encode("utf-8") + self.receive_id.encode("utf-8")
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted = base64.b64encode(
            encryptor.update(PKCS7Encoder.encode(payload)) + encryptor.finalize()
        ).decode("ascii")
        parts = sorted([self.token, timestamp, nonce, encrypted])
        sig = hashlib.sha1("".join(parts).encode()).hexdigest()
        root = _ET_BUILD.Element("xml")
        _ET_BUILD.SubElement(root, "Encrypt").text = encrypted
        _ET_BUILD.SubElement(root, "MsgSignature").text = sig
        _ET_BUILD.SubElement(root, "TimeStamp").text = timestamp
        _ET_BUILD.SubElement(root, "Nonce").text = nonce
        return _ET_BUILD.tostring(root, encoding="unicode")
