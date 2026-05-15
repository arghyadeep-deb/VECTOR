"""Channel stubs shim — re-exports from comms._stubs."""
from vectorcode.src.comms._stubs import *
from vectorcode.src.comms._stubs import ChannelStatus
from vectorcode.src.comms._stubs import ChannelMessage
from vectorcode.src.comms._stubs import BaseChannel

from typing import Callable
ChannelHandler = Callable[["ChannelMessage"], None]
