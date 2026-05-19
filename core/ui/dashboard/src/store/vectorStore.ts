import { create } from 'zustand'
import type { MemoryEvent, StatusResponse, AgentData, SystemMetrics, GoalsResponse, SecurityStatus, TaskSummary, CouncilSession, HealthData, TrainingData, LoopStatus, SchedulerData, InferenceStats, EmailData, ChannelsData, ProvidersData, ToolsRegistry, NetworkData, TokenJuiceData, AuditData, MeteringData, JupyterData, SandboxData, SensingData, MediaData, MiningData, MCPData, VideoData, ScraperData, SEOData, OAuthData, ResearchData, MigrationData } from '../lib/api'

export interface PanelEntry { id: string; type: 'mortality' | 'district' | 'decision'; districtName?: string }
interface ConnectionError { failed: boolean; lastError: string; retryCount: number }

export type AppMode = 'JARVIS_MODE' | 'DASHBOARD_MODE'

export interface ContentWindowEntry {
  id: string
  type: 'text' | 'camera' | 'map' | 'chart'
  title: string
  content?: string
  position?: { x: number; y: number }
}

export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking'

export interface VectorState {
  mode: AppMode
  bootDone: boolean
  processing: boolean
  voiceState: VoiceState
  contentWindows: ContentWindowEntry[]
  orbInCorner: boolean
  connected: boolean; status: StatusResponse | null; agents: AgentData[]; events: MemoryEvent[]; error: string | null
  activePanels: PanelEntry[]; connectionErrors: Record<string, ConnectionError>; lastUpdated: number
  quickResult: { title: string; lines: string[] } | null
  systemMetrics: SystemMetrics | null
  goals: GoalsResponse | null
  security: SecurityStatus | null
  tasks: TaskSummary | null
  councilHistory: CouncilSession[]
  openTaskbarPanel: 'core' | 'events' | 'metrics' | 'daily' | null
  showGlobe: boolean
  scrollTarget: { worldX: number; worldY: number; zoom?: number } | null
  health: HealthData | null
  trainingData: TrainingData | null
  loopStatus: LoopStatus | null
  scheduler: SchedulerData | null
  inference: InferenceStats | null
  email: EmailData | null
  channels: ChannelsData | null
  providers: ProvidersData | null
  tools: ToolsRegistry | null
  network: NetworkData | null
  tokenJuice: TokenJuiceData | null
  audit: AuditData | null
  metering: MeteringData | null
  jupyter: JupyterData | null
  sandbox: SandboxData | null
  sensing: SensingData | null
  media: MediaData | null
  mining: MiningData | null
  mcp: MCPData | null
  video: VideoData | null
  scraper: ScraperData | null
  seo: SEOData | null
  oauth: OAuthData | null
  research: ResearchData | null
  migration: MigrationData | null
  setMode: (m: AppMode) => void
  setBootDone: (v: boolean) => void
  setProcessing: (v: boolean) => void
  setVoiceState: (v: VoiceState) => void
  addContentWindow: (w: ContentWindowEntry) => void
  removeContentWindow: (id: string) => void
  clearContentWindows: () => void
  setOrbInCorner: (v: boolean) => void
  setShowGlobe: (v: boolean) => void
  setConnected: (v: boolean) => void; setStatus: (s: StatusResponse | null) => void; setAgents: (a: AgentData[]) => void
  addEvent: (e: MemoryEvent) => void; setEvents: (e: MemoryEvent[]) => void; setError: (e: string | null) => void
  openPanel: (entry: PanelEntry) => void; closePanel: (id: string) => void
  reportError: (endpoint: string, error: string) => void; clearError: (endpoint: string) => void
  setQuickResult: (r: { title: string; lines: string[] } | null) => void
  setSystemMetrics: (m: SystemMetrics | null) => void
  setGoals: (g: GoalsResponse | null) => void
  setSecurity: (s: SecurityStatus | null) => void
  setTasks: (t: TaskSummary | null) => void
  setCouncilHistory: (c: CouncilSession[]) => void
  setHealth: (h: HealthData | null) => void
  setTrainingData: (t: TrainingData | null) => void
  setLoopStatus: (d: LoopStatus | null) => void
  setScheduler: (d: SchedulerData | null) => void
  setInference: (d: InferenceStats | null) => void
  setEmail: (d: EmailData | null) => void
  setChannels: (d: ChannelsData | null) => void
  setProviders: (d: ProvidersData | null) => void
  setTools: (d: ToolsRegistry | null) => void
  setNetwork: (d: NetworkData | null) => void
  setTokenJuice: (d: TokenJuiceData | null) => void
  setAudit: (d: AuditData | null) => void
  setMetering: (d: MeteringData | null) => void
  setJupyter: (d: JupyterData | null) => void
  setSandbox: (d: SandboxData | null) => void
  setSensing: (d: SensingData | null) => void
  setMedia: (d: MediaData | null) => void
  setMining: (d: MiningData | null) => void
  setMcp: (d: MCPData | null) => void
  setVideo: (d: VideoData | null) => void
  setScraper: (d: ScraperData | null) => void
  setSeo: (d: SEOData | null) => void
  setOauth: (d: OAuthData | null) => void
  setResearch: (d: ResearchData | null) => void
  setMigration: (d: MigrationData | null) => void
  setOpenTaskbarPanel: (p: 'core' | 'events' | 'metrics' | 'daily' | null) => void
  scrollToPanel: (panelId: string) => void
  clearScrollTarget: () => void
}

const PANEL_POSITIONS: Record<string, { worldX: number; worldY: number }> = {
  /* Ring 1 (rf=0.80, rX=768, rY=432, 8 panels, chord gap at 45° = 380px) */
  telemetry: { worldX: 768, worldY: 0 },
  systemMetrics: { worldX: 543, worldY: 305 },
  events: { worldX: 0, worldY: 432 },
  compass: { worldX: -543, worldY: 305 },
  modelSwitcher: { worldX: -768, worldY: 0 },
  coreStatus: { worldX: -543, worldY: -305 },
  dailyInfo: { worldX: 0, worldY: -432 },
  vectorCode: { worldX: 543, worldY: -305 },
  /* Ring 2 (rf=1.25, rX=1200, rY=675, 10 panels) */
  health: { worldX: 971, worldY: 397 },
  training: { worldX: 371, worldY: 642 },
  goals: { worldX: -371, worldY: 642 },
  security: { worldX: -971, worldY: 397 },
  districts: { worldX: -1200, worldY: 0 },
  council: { worldX: -971, worldY: -397 },
  tasks: { worldX: -371, worldY: -642 },
  memory: { worldX: 371, worldY: -642 },
  loop: { worldX: 971, worldY: -397 },
  scheduler: { worldX: 1200, worldY: 0 },
  /* Ring 3 (rf=1.75, rX=1680, rY=945, 10 panels, offset 18°) */
  inference: { worldX: 1598, worldY: 292 },
  email: { worldX: 988, worldY: 765 },
  channels: { worldX: 0, worldY: 945 },
  providers: { worldX: -988, worldY: 765 },
  tools: { worldX: -1598, worldY: 292 },
  network: { worldX: -1598, worldY: -292 },
  audit: { worldX: -988, worldY: -765 },
  metering: { worldX: 0, worldY: -945 },
  jupyter: { worldX: 988, worldY: -765 },
  sandbox: { worldX: 1598, worldY: -292 },
  /* Ring 4 (rf=2.35, rX=2256, rY=1269, 10 panels, offset 36°) */
  sensing: { worldX: 1825, worldY: 746 },
  media: { worldX: 697, worldY: 1207 },
  mining: { worldX: -697, worldY: 1207 },
  mcp: { worldX: -1825, worldY: 746 },
  video: { worldX: -2256, worldY: 0 },
  scraper: { worldX: -1825, worldY: -746 },
  seo: { worldX: -697, worldY: -1207 },
  oauth: { worldX: 697, worldY: -1207 },
  research: { worldX: 1825, worldY: -746 },
  migration: { worldX: 2256, worldY: 0 },
  /* Ring 5 */
  brain: { worldX: 3300, worldY: 0 },
  city: { worldX: 2926, worldY: 859 },
  control: { worldX: 1874, worldY: 1528 },
  finance: { worldX: 396, worldY: 1843 },
  design: { worldX: -1169, worldY: 1736 },
  analytics: { worldX: -2471, worldY: 1230 },
  privacy: { worldX: -3210, worldY: 431 },
  coding_district: { worldX: -3210, worldY: -431 },
  qa_district: { worldX: -2471, worldY: -1230 },
  projects_district: { worldX: -1169, worldY: -1736 },
  learning: { worldX: 396, worldY: -1843 },
  interview: { worldX: 1874, worldY: -1528 },
  languages: { worldX: 2926, worldY: -859 },
  /* Ring 6 */
  news: { worldX: 4078, worldY: 565 },
  patterns: { worldX: 3146, worldY: 1565 },
  reflection: { worldX: 1488, worldY: 2210 },
  relationships: { worldX: -504, worldY: 2347 },
  skills: { worldX: -2385, worldY: 1945 },
  startups: { worldX: -3724, worldY: 1094 },
  karpathy: { worldX: -4200, worldY: 0 },
  ops: { worldX: -3724, worldY: -1094 },
  chief: { worldX: -2385, worldY: -1945 },
  calls: { worldX: -504, worldY: -2347 },
  agency: { worldX: 1488, worldY: -2210 },
  documentation: { worldX: 3146, worldY: -1565 },
  governance: { worldX: 4078, worldY: -565 },
}

export const useVectorStore = create<VectorState>()((set) => ({
  mode: 'JARVIS_MODE',
  bootDone: false,
  processing: false,
  contentWindows: [],
  orbInCorner: false,
  connected: false,
  status: null,
  agents: [],
  events: [],
  error: null,
  activePanels: [],
  connectionErrors: {},
  lastUpdated: 0,
  quickResult: null,
  systemMetrics: null,
  goals: null,
  security: null,
  tasks: null,
  councilHistory: [],
  openTaskbarPanel: null,
  showGlobe: false,
  scrollTarget: null,
  health: null,
  trainingData: null,
  loopStatus: null,
  scheduler: null,
  inference: null,
  email: null,
  channels: null,
  providers: null,
  tools: null,
  network: null,
  tokenJuice: null,
  audit: null,
  metering: null,
  jupyter: null,
  sandbox: null,
  sensing: null,
  media: null,
  mining: null,
  mcp: null,
  video: null,
  scraper: null,
  seo: null,
  oauth: null,
  research: null,
  migration: null,

  setMode: (m) => set({ mode: m }),
  setBootDone: (v) => set({ bootDone: v }),
  setProcessing: (v) => set({ processing: v }),
  addContentWindow: (w) => set((s) => ({ contentWindows: [...s.contentWindows, w], orbInCorner: true })),
  removeContentWindow: (id) => set((s) => {
    const remaining = s.contentWindows.filter(w => w.id !== id)
    return { contentWindows: remaining, orbInCorner: remaining.length > 0 }
  }),
  clearContentWindows: () => set({ contentWindows: [], orbInCorner: false }),
  setOrbInCorner: (v) => set({ orbInCorner: v }),
  setShowGlobe: (v) => set({ showGlobe: v }),
  setConnected: (v) => set({ connected: v }),
  setStatus: (s) => set({ status: s, lastUpdated: Date.now() }),
  setAgents: (a) => set({ agents: a, lastUpdated: Date.now() }),
  addEvent: (e) => set((state) => ({ events: [e, ...state.events].slice(0, 50) })),
  setEvents: (e) => set({ events: e }),
  setError: (e) => set({ error: e }),
  openPanel: (entry) => set((state) => ({ activePanels: [...state.activePanels.filter((p) => p.type !== entry.type), entry] })),
  closePanel: (id) => set((state) => ({ activePanels: state.activePanels.filter((p) => p.id !== id) })),
  reportError: (endpoint, error) => set((state) => ({ connectionErrors: { ...state.connectionErrors, [endpoint]: { failed: true, lastError: error, retryCount: (state.connectionErrors[endpoint]?.retryCount ?? 0) + 1 } } })),
  clearError: (endpoint) => set((state) => { const n = { ...state.connectionErrors }; delete n[endpoint]; return { connectionErrors: n } }),
  setQuickResult: (r) => set({ quickResult: r }),
  setSystemMetrics: (m) => set({ systemMetrics: m }),
  setGoals: (g) => set({ goals: g }),
  setSecurity: (s) => set({ security: s }),
  setTasks: (t) => set({ tasks: t }),
  setCouncilHistory: (c) => set({ councilHistory: c }),
  setHealth: (h) => set({ health: h }),
  setTrainingData: (t) => set({ trainingData: t }),
  setLoopStatus: (d) => set({ loopStatus: d }),
  setScheduler: (d) => set({ scheduler: d }),
  setInference: (d) => set({ inference: d }),
  setEmail: (d) => set({ email: d }),
  setChannels: (d) => set({ channels: d }),
  setProviders: (d) => set({ providers: d }),
  setTools: (d) => set({ tools: d }),
  setNetwork: (d) => set({ network: d }),
  setTokenJuice: (d) => set({ tokenJuice: d }),
  setAudit: (d) => set({ audit: d }),
  setMetering: (d) => set({ metering: d }),
  setJupyter: (d) => set({ jupyter: d }),
  setSandbox: (d) => set({ sandbox: d }),
  setSensing: (d) => set({ sensing: d }),
  setMedia: (d) => set({ media: d }),
  setMining: (d) => set({ mining: d }),
  setMcp: (d) => set({ mcp: d }),
  setVideo: (d) => set({ video: d }),
  setScraper: (d) => set({ scraper: d }),
  setSeo: (d) => set({ seo: d }),
  setOauth: (d) => set({ oauth: d }),
  setResearch: (d) => set({ research: d }),
  setMigration: (d) => set({ migration: d }),
  setOpenTaskbarPanel: (p: 'core' | 'events' | 'metrics' | 'daily' | null) => set((state) => ({ openTaskbarPanel: state.openTaskbarPanel === p ? null : p })),

  scrollToPanel: (panelId: string) => {
    const pos = PANEL_POSITIONS[panelId]
    if (pos) {
      set({ scrollTarget: { worldX: pos.worldX, worldY: pos.worldY, zoom: 2.5 } })
    }
  },

  clearScrollTarget: () => set({ scrollTarget: null }),
}))
