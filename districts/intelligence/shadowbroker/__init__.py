"""VECTOR Shadowbroker SDK — absorbed from Shadowbroker-main openclaw-skills.

Adds this directory to sys.path so the SDK modules can find each other
using their original bare imports (e.g. `from sb_signatures import sig`).
"""
import sys
from pathlib import Path

_SDK_DIR = str(Path(__file__).parent)
if _SDK_DIR not in sys.path:

from sb_query import ShadowBrokerClient  # noqa: E402
from sb_alerts import AlertDispatcher     # noqa: E402
from sb_signatures import sig             # noqa: E402

__all__ = ["ShadowBrokerClient", "AlertDispatcher", "sig"]
