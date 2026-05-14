import { create } from 'zustand'
import type { MemoryEvent, StatusResponse, AgentData, SystemMetrics, GoalsResponse } from '../lib/api'

export interface PanelEntry { id: string; type: 'mortality' | 'district' | 'decision'; districtName?: string }
interface ConnectionError { failed: boolean; lastError: string; retryCount: number }

export interface VectorState {
  connected: boolean; status: StatusResponse | null; agents: AgentData[]; events: MemoryEvent[]; error: string | null
  activePanels: PanelEntry[]; connectionErrors: Record<string, ConnectionError>; lastUpdated: number
  quickResult: { title: string; lines: string[] } | null
  systemMetrics: SystemMetrics | null
  goals: GoalsResponse | null
  // Taskbar panel visibility
  openTaskbarPanel: 'core' | 'events' | 'metrics' | 'daily' | null
  setConnected: (v: boolean) => void; setStatus: (s: StatusResponse | null) => void; setAgents: (a: AgentData[]) => void
  addEvent: (e: MemoryEvent) => void; setEvents: (e: MemoryEvent[]) => void; setError: (e: string | null) => void
  openPanel: (entry: PanelEntry) => void; closePanel: (id: string) => void
  reportError: (endpoint: string, error: string) => void; clearError: (endpoint: string) => void
  setQuickResult: (r: { title: string; lines: string[] } | null) => void
  setSystemMetrics: (m: SystemMetrics | null) => void
  setGoals: (g: GoalsResponse | null) => void
  setOpenTaskbarPanel: (p: 'core' | 'events' | 'metrics' | 'daily' | null) => void
}

export const useVectorStore = create<VectorState>()((set) => ({
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
  openTaskbarPanel: null,

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
  setOpenTaskbarPanel: (p: 'core' | 'events' | 'metrics' | 'daily' | null) => set((state) => ({ openTaskbarPanel: state.openTaskbarPanel === p ? null : p })),
}))
