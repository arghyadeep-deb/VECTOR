const BASE = process.env.NEXT_PUBLIC_VECTOR_API ?? 'http://127.0.0.1:8000';
const WS_BASE = (process.env.NEXT_PUBLIC_VECTOR_WS ?? 'ws://127.0.0.1:8000') + '/ws';

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ── Types ──────────────────────────────────────────────

export interface StatusResponse {
  loop_running: boolean;
  uptime_seconds: number;
  models: Record<string, string>;
  memory: Record<string, unknown>;
  agents: { count: number; districts: string[]; alive?: number; elite?: number; list?: any[] };
  vector_version: string;
}

export interface HealthResponse {
  status: string;
  checks: Record<string, string>;
  timestamp: string;
  version: string;
}

export interface Agent {
  id: string;
  name: string;
  district: string;
  status: string;
  hp?: number;
  health_points?: number;
  last_action?: string;
  task_count?: number;
  [key: string]: unknown;
}

export interface AgentListResponse {
  agents: Agent[];
  count: number;
  error?: string;
}

export interface MemoryEvent {
  id?: string;
  timestamp: string;
  event_type: string;
  content: string;
  importance?: string;
  tags?: string[];
  context?: Record<string, unknown>;
  source?: string;
}

export interface MemoryRecentResponse {
  events: MemoryEvent[];
  count: number;
  error?: string;
}

export interface GoalsResponse {
  immediate_actions: Array<Record<string, unknown>>;
  error?: string;
}

export interface CouncilHistoryResponse {
  sessions: MemoryEvent[];
  count: number;
  error?: string;
}

export interface CouncilRequest {
  question: string;
  stakes?: 'medium' | 'high' | 'critical';
}

export interface CouncilResponse {
  decision: string;
  confidence: number;
  session_id?: string;
  chairman_decision?: string;
  stored_as_training_data: boolean;
}

export interface SecurityRecentResponse {
  events: MemoryEvent[];
  count: number;
  error?: string;
}

export interface CommandRequest {
  text: string;
  priority?: 'low' | 'normal' | 'high';
}

export interface CommandResponse {
  response: string;
  success?: boolean;
  error?: string;
}

// ── API calls ──────────────────────────────────────────

export const api = {
  status:          () => get<StatusResponse>('/status'),
  health:          () => get<HealthResponse>('/health'),
  agents:          () => get<AgentListResponse>('/agents'),
  memoryRecent:    (limit = 20) => get<MemoryRecentResponse>(`/memory/recent?limit=${limit}`),
  memoryGoals:     () => get<GoalsResponse>('/memory/goals'),
  councilHistory:  (limit = 5) => get<CouncilHistoryResponse>(`/memory/council/history?limit=${limit}`),
  securityRecent:  (limit = 15) => get<SecurityRecentResponse>(`/security/recent?limit=${limit}`),
  securityStatus:  () => get<any>('/security/status'),
  voiceStatus:     () => get<any>('/voice/status'),
  council:         (body: CouncilRequest) => post<CouncilResponse>('/council', body),
  executeCommand:  (text: string) => post<CommandResponse>('/ws/command', { text }),
};

// ── WebSocket ──────────────────────────────────────────

export type WSMessage =
  | { type: 'status'; [key: string]: any }
  | { type: 'events'; events: MemoryEvent[]; [key: string]: any }
  | { type: 'response'; response?: string; [key: string]: any }
  | { type: 'error'; detail: string }
  | { type: 'ping' | 'pong'; time: string }
  | { type: 'subscribed'; channel: string };

export interface WSCallbacks {
  onConnect?: () => void;
  onDisconnect?: () => void;
  onStatus?: (data: StatusResponse) => void;
  onEvent?: (event: MemoryEvent) => void;
  onCommandResponse?: (response: { response?: string; [key: string]: any }) => void;
  onError?: (e: Event) => void;
}

export class VectorWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private callbacks: WSCallbacks = {};

  constructor(url: string = WS_BASE) {
    this.url = url;
  }

  get onConnect() { return this.callbacks.onConnect; }
  set onConnect(v) { this.callbacks.onConnect = v; }
  get onDisconnect() { return this.callbacks.onDisconnect; }
  set onDisconnect(v) { this.callbacks.onDisconnect = v; }
  get onStatus() { return this.callbacks.onStatus; }
  set onStatus(v) { this.callbacks.onStatus = v; }
  get onEvent() { return this.callbacks.onEvent; }
  set onEvent(v) { this.callbacks.onEvent = v; }
  get onCommandResponse() { return this.callbacks.onCommandResponse; }
  set onCommandResponse(v) { this.callbacks.onCommandResponse = v; }
  get onError() { return this.callbacks.onError; }
  set onError(v) { this.callbacks.onError = v; }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    try {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => {
        this.callbacks.onConnect?.();
      };
      this.ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as WSMessage;
          if (msg.type === 'status') {
            this.callbacks.onStatus?.(msg as unknown as StatusResponse);
          } else if (msg.type === 'events' && msg.events?.[0]) {
            msg.events.forEach((e) => this.callbacks.onEvent?.(e));
          } else if (msg.type === 'response') {
            this.callbacks.onCommandResponse?.(msg);
          }
        } catch {
          // ignore parse errors
        }
      };
      this.ws.onclose = () => {
        this.callbacks.onDisconnect?.();
        this.scheduleReconnect();
      };
      this.ws.onerror = (e) => {
        this.callbacks.onError?.(e);
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  subscribe(channel: string) {
    this.send({ action: 'subscribe', channel });
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(data: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  command(text: string, priority = 'normal') {
    this.send({ action: 'command', text, priority });
  }

  ping() {
    this.send({ action: 'ping' });
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 3000);
  }
}

// ── Helpers ────────────────────────────────────────────

export function formatUptime(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}

export function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return ts?.slice(11, 19) ?? '—'; }
}

export function modelColor(s: string) {
  if (s === 'loaded')       return 'chip-cyan';
  if (s === 'unloaded')     return 'chip-muted';
  if (s === 'unavailable')  return 'chip-amber';
  return 'chip-muted';
}

export function hpColor(hp: number): string {
  if (hp >= 800) return '#00ff88';
  if (hp >= 600) return '#00dddd';
  if (hp >= 400) return '#00aaff';
  if (hp >= 200) return '#ffaa00';
  return '#ff4444';
}

export function statusGlow(status: string): string {
  if (status === 'elite') return '0 0 12px rgba(0,255,136,0.5)';
  if (status === 'strong') return '0 0 10px rgba(0,221,221,0.4)';
  if (status === 'dead') return '0 0 8px rgba(255,68,68,0.4)';
  return '0 0 6px rgba(0,170,255,0.3)';
}
