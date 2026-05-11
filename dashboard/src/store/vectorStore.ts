import { create } from 'zustand';

export interface AgentData {
  id: string;
  name: string;
  district: string;
  health_points: number;
  status: string;
  is_alive: boolean;
  model?: string;
  generation?: number;
}

export interface MemoryEvent {
  id?: string;
  timestamp: string;
  event_type: string;
  content: string;
  tags?: string[];
  source?: string;
}

export interface VectorStatus {
  loop_running: boolean;
  uptime_seconds: number;
  models: Record<string, string>;
  memory: Record<string, any>;
  agents: {
    count: number;
    districts: string[];
    alive?: number;
    elite?: number;
    list?: AgentData[];
  };
  vector_version: string;
}

export interface VectorState {
  // Connection
  connected: boolean;
  connecting: boolean;
  lastPing: number;
  error: string | null;

  // Data
  status: VectorStatus | null;
  agents: AgentData[];
  events: MemoryEvent[];
  commandResponse: any | null;

  // UI
  activePanel: string | null;
  voiceActive: boolean;

  // Actions
  setConnected: (v: boolean) => void;
  setConnecting: (v: boolean) => void;
  setStatus: (s: VectorStatus | null) => void;
  setAgents: (a: AgentData[]) => void;
  addEvent: (e: MemoryEvent) => void;
  setEvents: (e: MemoryEvent[]) => void;
  setCommandResponse: (r: any) => void;
  addCommandResponse: (r: any) => void;
  setActivePanel: (p: string | null) => void;
  setVoiceActive: (v: boolean) => void;
  setError: (e: string | null) => void;
  setLastPing: (t: number) => void;
}

export const useVectorStore = create<VectorState>((set) => ({
  connected: false,
  connecting: false,
  lastPing: 0,
  error: null,
  status: null,
  agents: [],
  events: [],
  commandResponse: null,
  activePanel: null,
  voiceActive: false,

  setConnected: (v) => set({ connected: v }),
  setConnecting: (v) => set({ connecting: v }),
  setStatus: (s) => set({ status: s }),
  setAgents: (a) => set({ agents: a }),
  addEvent: (e) => set((state) => ({ events: [e, ...state.events].slice(0, 50) })),
  setEvents: (e) => set({ events: e }),
  setCommandResponse: (r) => set({ commandResponse: r }),
  addCommandResponse: (r) => set((state) => ({ commandResponse: r })),
  setActivePanel: (p) => set({ activePanel: p }),
  setVoiceActive: (v) => set({ voiceActive: v }),
  setError: (e) => set({ error: e }),
  setLastPing: (t) => set({ lastPing: t }),
}));
