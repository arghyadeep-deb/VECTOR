"""Pydantic schemas for V.E.C.T.O.R. API."""

import sys

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import datetime

# --- Request Models ---

class CommandRequest(BaseModel):
    text: str
    source: str = "text"
    priority: str = "normal"
    # 2026-07-29: optional per-session rolling conversational buffer
    # (core.memory.session_buffer). Callers that never set this see
    # IDENTICAL behavior to before this field existed — every buffer
    # read/write in commands.py is gated on `if body.session_id`.
    session_id: Optional[str] = None

class VoiceRequest(BaseModel):
    # Voice request would typically be multipart/form-data
    pass

class AgentAwardRequest(BaseModel):
    agent_id: str
    points: int
    reason: str

class CouncilRequest(BaseModel):
    question: str
    stakes: str = "medium"
    context_override: Optional[Dict[str, Any]] = None

# --- Response Models ---

class CommandResponse(BaseModel):
    response: str
    action_taken: Optional[str] = None
    candidates_evaluated: int = 0
    winner_score: float = 0.0
    memory_updated: bool = False
    processing_ms: int = 0
    # 2026-07-21 KNOWN_ISSUES #1: surfaces which district actually handled
    # this request when it went through Governor.dispatch() (real-district
    # requests only — None for plain Q&A and for the older keyword-matched
    # PermissionGateway actions, which have no district concept). Lets eval
    # scripts / trace metadata see routing decisions instead of a black box.
    district: Optional[str] = None

class VoiceResponse(BaseModel):
    transcript: str
    response: str
    language_detected: str

class AgentAwardResponse(BaseModel):
    new_hp: int
    status: str
    model_upgraded: bool
    agent: Optional[Dict[str, Any]] = None
    award: Optional[Dict[str, Any]] = None

class CouncilResponse(BaseModel):
    decision: str
    confidence: float
    session_id: Optional[str] = None
    chairman_decision: Optional[str] = None
    winning_model: Optional[str] = None
    stored_as_training_data: bool = False

class StatusResponse(BaseModel):
    loop_running: bool
    uptime_seconds: int
    models: Dict[str, str]
    memory: Dict[str, Any]
    agents: Dict[str, Any]
    vector_version: str
    last_reflect: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    checks: Dict[str, str]
    timestamp: str
    version: str
    # 2026-08-05 (KNOWN_ISSUES #0): checks["loop"] carries the short tri-state
    # ("ok" | "stale" | "not_started") that decides whether `status` flips;
    # loop_detail carries the debug payload (heartbeat age, owning pid, tick
    # count, whether this deployment opted out via VECTOR_API_RUN_LOOP=0) so
    # the HUD/a human can tell WHY without re-deriving it from the heartbeat
    # file. Optional + defaulted so existing consumers of checks/status are
    # unaffected.
    loop_detail: Optional[Dict[str, Any]] = None

class AgentListResponse(BaseModel):
    agents: List[Dict[str, Any]]
    count: int
    error: Optional[str] = None

class MemoryRecentResponse(BaseModel):
    events: List[Dict[str, Any]]
    count: int
    error: Optional[str] = None

class GoalsResponse(BaseModel):
    immediate_actions: List[Dict[str, Any]]
    error: Optional[str] = None

class CouncilHistoryResponse(BaseModel):
    sessions: List[Dict[str, Any]]
    count: int
    error: Optional[str] = None

class SecurityRecentResponse(BaseModel):
    events: List[Dict[str, Any]]
    count: int
    error: Optional[str] = None

class ProcessInfo(BaseModel):
    name: str
    cpu: float
    mem: float
    status: str

class PermissionAuditEntry(BaseModel):
    timestamp: str
    action_type: str
    level: str
    approved: bool
    executed: bool
    proposed_by: str
    reason: str

class SecurityStatusResponse(BaseModel):
    threat_level: str
    active_scans: int
    anomalies_found: int
    sandbox_status: str
    processes: List[ProcessInfo]
    audit_log: List[PermissionAuditEntry]

# --- WebSocket Message Models ---

class WSStatusPayload(BaseModel):
    type: str = "status"
    timestamp: str
    loop_running: bool
    uptime_seconds: int
    models: Dict[str, str]
    memory: Dict[str, Any]
    agents: Dict[str, Any]
    vector_version: str

class WSEventsPayload(BaseModel):
    type: str = "events"
    timestamp: str
    events: List[Dict[str, Any]]
    error: Optional[str] = None

class WSCommandRequest(BaseModel):
    action: str = "command"
    text: str
    priority: str = "normal"

class WSCommandResponse(BaseModel):
    type: str = "response"
    action: str
    approved: bool
    level: str
    score: float
    reasoning: str
    timestamp: str

class WSErrorPayload(BaseModel):
    type: str = "error"
    detail: str

class WSPingPayload(BaseModel):
    type: str = "ping"
    time: str

class WSPongPayload(BaseModel):
    type: str = "pong"
    time: str

# --- New Router Response Models ---

class LoopStatusResponse(BaseModel):
    running: bool
    tick_count: int
    uptime_seconds: int
    guard_violations: list
    task_queue_depth: int

class SchedulerJobsResponse(BaseModel):
    total: int
    active: int
    jobs: list

class InferenceStatsResponse(BaseModel):
    total_models: int
    loaded_models: int
    model_list: list[str]
    status: str

class EmailRecentResponse(BaseModel):
    total: int
    unread: int
    recent: list

class ChannelsStatusResponse(BaseModel):
    active_channels: list[str]
    recent_messages: int
    status: str

class ProvidersRoutesResponse(BaseModel):
    routes: dict[str, str]
    active_providers: list[str]

class ToolsRegistryResponse(BaseModel):
    total_tools: int
    scopes: list[str]
    permission_levels: dict[str, int]

class NetworkPeersResponse(BaseModel):
    total_peers: int
    peers: list

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ schemas.py OK")
