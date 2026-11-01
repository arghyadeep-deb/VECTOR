"""Channel stubs shim — re-exports from comms._abc."""
from vectorcode.src.comms._abc import *
from vectorcode.src.comms._abc import ChannelStatus
from vectorcode.src.comms._abc import ChannelMessage
from vectorcode.src.comms._abc import BaseChannel

from typing import Callable
ChannelHandler = Callable[["ChannelMessage"], None]
