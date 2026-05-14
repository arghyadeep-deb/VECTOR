// All API calls go through this module — no business logic in the frontend.
// The frontend only calls backend endpoints; it never computes decisions itself.

const BASE = ''

// ── CSRF Token ────────────────────────────────────────────────────────────────
let _csrfToken = ''

async function fetchCsrfToken(): Promise<string> {
  try {
    const r = await fetch(`${BASE}/csrf-token`, { cache: 'no-store' })
    const d = await r.json()
    _csrfToken = d.csrf_token ?? ''
    return _csrfToken
  } catch {
    return ''
  }
}

// Fetch CSRF token on module load
fetchCsrfToken()

// ── HTTP helpers ──────────────────────────────────────────────────────────────
async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  // Refresh CSRF token if missing
  if (!_csrfToken) await fetchCsrfToken()
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': _csrfToken,
    },
    body: JSON.stringify(body),
    cache: 'no-store',
  })
  if (!r.ok) {
    // If CSRF expired, refresh and retry once
    if (r.status === 403) {
      await fetchCsrfToken()
      const retry = await fetch(`${BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': _csrfToken },
        body: JSON.stringify(body),
        cache: 'no-store',
      })
      if (!retry.ok) throw new Error(`${retry.status} ${retry.statusText}`)
      return retry.json()
    }
    throw new Error(`${r.status} ${r.statusText}`)
  }
  return r.json()
}

// ── Response types ────────────────────────────────────────────────────────────
export interface StatusResponse {
  loop_running: boolean
  uptime_seconds: number
  models: Record<string, string>
  memory: Record<string, unknown>
  agents: { count: number; districts: string[]; alive?: number; elite?: number; list?: any[] }
  vector_version: string
  last_reflect?: string | null
}

export interface MemoryEvent {
  id?: string
  timestamp: string
  event_type: string
  content: string
  importance?: string
  tags?: string[]
  source?: string
}

export interface MemoryRecentResponse {
  events: MemoryEvent[]
  count: number
}

export interface AgentData {
  id: string
  name: string
  district: string
  health_points: number
  status: string
  is_alive: boolean
  model?: string
  generation?: number
}

export interface AgentListResponse {
  agents: AgentData[]
  count: number
}

export interface GoalsResponse {
  immediate_actions: Array<Record<string, unknown>>
}

export interface SystemMetrics {
  cpu_percent: number
  memory_percent: number
  memory_used_gb: number
  memory_total_gb: number
  disk_percent: number
  disk_used_gb: number
  disk_total_gb: number
  net_sent_mb: number
  net_recv_mb: number
  net_sent_rate_mbs: number
  net_recv_rate_mbs: number
  gpu_percent: number | null
  gpu_temp_c: number | null
  gpu_mem_percent: number | null
  uptime_seconds: number
}

export interface CommandResponse {
  response: string
  action_taken?: string | null
  candidates_evaluated?: number
  winner_score?: number
  memory_updated?: boolean
  processing_ms?: number
}

export interface FeedbackResponse {
  status: string
  action_type: string
  reward: number
  rating: number
}

// ── API surface — all calls go to backend, no logic here ──────────────────────
export const api = {
  status: () => get<StatusResponse>('/status'),
  agents: () => get<AgentListResponse>('/agents'),
  system: () => get<SystemMetrics>('/system'),
  memoryRecent: (limit = 20) => get<MemoryRecentResponse>(`/memory/recent?limit=${limit}`),
  goals: () => get<GoalsResponse>('/memory/goals'),

  // Send a command to VECTOR — backend handles all routing/decision logic
  command: (text: string, source: 'text' | 'voice' = 'text') =>
    post<CommandResponse>('/command', { text, source, priority: 'normal' }),

  // Submit feedback on an action — backend updates RL policy
  feedback: (action_type: string, rating: 1 | 2 | 3 | 4 | 5, note = '') =>
    post<FeedbackResponse>('/command/feedback', { action_type, rating, note }),

  // Trigger LLM council — backend handles deliberation
  council: (question: string, stakes: 'medium' | 'high' | 'critical' = 'medium') =>
    post<{ verdict: string; session_id: string }>('/council', { question, stakes }),

  // Daily briefing: weather, location, date
  daily: () => get<{
    date: string; time: string; location: string | null
    weather: { temp_c: number; feels_c: number; humidity_pct: number; wind_kmh: number; description: string; code: number } | null
    sunrise: string | null; sunset: string | null
  }>('/daily'),

  // Award/deduct HP — backend validates and applies
  agentAward: (agent_id: string, points: number, reason: string) =>
    post<{ new_hp: number; status: string }>('/agent/award', { agent_id, points, reason }),
}

// ── Utility functions (pure, no API calls) ────────────────────────────────────
export function formatUptime(s: number): string {
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}

export function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return ts?.slice(11, 19) ?? '—' }
}

export function hpColor(hp: number): string {
  if (hp >= 800) return '#00CFFF'
  if (hp >= 600) return '#00ff88'
  if (hp >= 400) return '#ffaa00'
  if (hp >= 200) return '#ff8800'
  return '#ff4444'
}

// Legacy compat
export async function fetchStatus(path: string) {
  const r = await fetch(`${document.location.origin}${path}`, { cache: 'no-store' })
  return r.json()
}
