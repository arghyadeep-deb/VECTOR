import hashlib
from core.memory.episodic import _get_db_key


def test_db_key_fingerprint():
    k = _get_db_key()
    print(f"\npytest: key length = {len(k)} | sha256 fingerprint = {hashlib.sha256(k.encode()).hexdigest()[:8]}")
