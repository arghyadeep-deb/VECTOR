"""VECTOR Shadowbroker SDK — absorbed from Shadowbroker-main openclaw-skills."""
from .sb_query import ShadowBrokerClient
from .sb_alerts import AlertDispatcher
from .sb_signatures import sig

__all__ = ["ShadowBrokerClient", "AlertDispatcher", "sig"]
