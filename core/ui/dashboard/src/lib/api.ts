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

export interface SecurityStatus {
  threat_level: string
  active_scans: number
  anomalies_found: number
  processes?: Array<{ name: string; cpu: number; mem: number; status: string }>
  audit_log?: Array<{ timestamp: string; action_type: string; level: string; approved: boolean }>
}

export interface CouncilSession {
  session_id: string
  decision: string
  confidence: number
  members?: string[]
  timestamp?: string
}

export interface TaskSummary {
  queued: number
  running: number
  completed: number
  failed: number
  tasks?: Array<{ id: string; name: string; status: string; district: string; priority: string; created_at: string }>
}

export interface LoopStatus { running: boolean; tick_count: number; uptime_seconds: number; guard_violations: any[]; task_queue_depth: number }
export interface SchedulerData { total: number; active: number; jobs: any[] }
export interface InferenceStats { total_models: number; loaded_models: number; model_list: string[]; status: string }
export interface EmailData { total: number; unread: number; recent: Array<{id: string; subject: string; sender: string; date: string; read: number}> }
export interface ChannelsData { active_channels: string[]; recent_messages: number; status: string }
export interface ProvidersData { routes: Record<string, string>; active_providers: string[] }
export interface ToolsRegistry { total_tools: number; scopes: string[]; permission_levels: Record<string, number> }
export interface NetworkData { total_peers: number; peers: Array<{node_id: string; host: string; port: number; last_seen: number}> }
export interface TokenJuiceData { compression_ratio: number; tokens_saved: number; total_processed: number }
export interface ConfigData { ollama_host: string; log_level: string; vector_version: string; districts: string[] }

export interface AuditData { total: number; verified: boolean; entries: Array<{sequence: number; timestamp: string; action: string; agent_id: string; district: string}> }
export interface MeteringData { total_spent: number; budget_limit: number; usage_pct: number; period: string }
export interface JupyterData { active_sessions: number; sessions_dir: string }
export interface SandboxData { docker_available: boolean; status: string }
export interface SensingData { fatigue_score: number; energy_level: string; system_load: {cpu_percent: number; ram_percent: number}; camera_available: boolean }
export interface MediaData { total_models: number; categories: Record<string, number>; models: string[] }
export interface MiningData { shares_submitted: number; shares_accepted: number; blocks_found: number; errors: number; running: boolean }
export interface MCPData { fastmcp_available: boolean; vc_mcp_available: boolean; status: string }
export interface VideoData { total_compositions: number; compositions: string[] }
export interface ScraperData { fetcher_types: string[]; stealth_available: boolean; dynamic_available: boolean }
export interface SEOData { pagespeed_configured: boolean; gsc_configured: boolean; tools: string[] }
export interface OAuthData { total_integrations: number; categories: Record<string, number>; available: number }
export interface ResearchData { modes: string[]; llm_available: boolean }
export interface MigrationData { sources: string[]; total_sources: number }

export interface HealthData {
  status: string
  checks: Record<string, string>
  timestamp: string
  version: string
}

export interface TrainingData {
  entries: Array<{ id: string; timestamp: string; content: string; source: string }>
  count: number
  status: string
}

export interface NudgeData {
  text: string
  rule: string
  timestamp: string
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

  // Voice: send audio blob to Whisper STT pipeline — backend handles everything
  voice: async (blob: Blob): Promise<{ transcript: string; response: string; language_detected: string }> => {
    const form = new FormData()
    form.append('audio', blob, 'voice.webm')
    const r = await fetch(`${BASE}/voice`, { method: 'POST', body: form, cache: 'no-store' })
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
    return r.json()
  },

  securityStatus: () => get<SecurityStatus>('/security/status'),
  tasks: () => get<TaskSummary>('/tasks/'),
  councilHistory: (limit = 5) => get<{ sessions: CouncilSession[] }>(`/memory/council/history?limit=${limit}`),
  nudge: () => get<{ text: string; rule: string; timestamp: string }>('/nudge/latest'),
  health: () => get<HealthData>('/status/health'),
  trainingData: (limit = 10) => get<TrainingData>(`/memory/training-data?limit=${limit}`),
  loopStatus: () => get<LoopStatus>('/loop/status'),
  schedulerJobs: () => get<SchedulerData>('/scheduler/jobs'),
  inferenceStats: () => get<InferenceStats>('/inference/stats'),
  emailRecent: () => get<EmailData>('/email/recent'),
  channelsStatus: () => get<ChannelsData>('/channels/status'),
  providerRoutes: () => get<ProvidersData>('/providers/routes'),
  toolsRegistry: () => get<ToolsRegistry>('/tools/registry'),
  networkPeers: () => get<NetworkData>('/network/peers'),

  auditRecent: (limit = 10) => get<AuditData>(`/audit/recent?limit=${limit}`),
  meteringStatus: () => get<MeteringData>('/metering/status'),
  jupyterSessions: () => get<JupyterData>('/vector-harness/sessions'),
  sandboxStatus: () => get<SandboxData>('/sandbox/status'),
  sensingStatus: () => get<SensingData>('/sensing/status'),
  mediaModels: () => get<MediaData>('/media/models'),
  miningStatus: () => get<MiningData>('/mining/status'),
  mcpStatus: () => get<MCPData>('/mcp/status'),
  videoCompositions: () => get<VideoData>('/video/compositions'),
  scraperStatus: () => get<ScraperData>('/scraper/status'),
  seoStatus: () => get<SEOData>('/seo/status'),
  oauthIntegrations: () => get<OAuthData>('/oauth/integrations'),
  researchStatus: () => get<ResearchData>('/research/status'),
  migrationSources: () => get<MigrationData>('/migration/sources'),

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
