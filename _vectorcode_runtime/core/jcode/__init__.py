"""
VECTOR Agent Engine — ported from high-performance agent harness.

Unique capabilities not present in vectorcode:
  cache_tracker      : KV cache append-only violation detection
  tools.multiedit    : atomic multi-edit on a single file
  tools.apply_patch  : Codex-style *** Begin Patch / *** End Patch
  ambient_scheduler  : rich directive system with 3-way targeting
  session_persistence: disk-backed sessions with crash recovery
"""
from core.jcode.cache_tracker import CacheTracker, CacheViolation
from core.jcode.tools.multiedit import multiedit
from core.jcode.tools.apply_patch import apply_patch
from core.jcode.ambient_scheduler import (
    AmbientStatus, AmbientScheduler, ScheduledItem, ScheduleTarget, Priority
)
from core.jcode.session_persistence import SessionPersistence

__all__ = [
    "CacheTracker", "CacheViolation",
    "multiedit", "apply_patch",
    "AmbientStatus", "AmbientScheduler", "ScheduledItem", "ScheduleTarget", "Priority",
    "SessionPersistence",
]
