import type { StatusResponse, AgentData, SystemMetrics, GoalsResponse, MemoryEvent } from './api'

let tick = 0

function rand(min: number, max: number) { return Math.round(min + Math.random() * (max - min)) }

function fluctuate(v: number, range: number): number {
  return Math.max(0, Math.min(100, v + (Math.random() - 0.5) * range))
}

export function mockStatus(): StatusResponse {
  tick++
  return {
    loop_running: true,
    uptime_seconds: tick * 5 + 36000,
    models: { default: 'gpt-4', fast: 'claude-3-haiku' },
    memory: {
      episodic_count: 1200 + Math.floor(tick * 0.5),
      semantic_count: 850,
      procedural_count: 320,
    },
    agents: {
      count: 12,
      districts: ['coding', 'finance', 'governance', 'health', 'memory_curator', 'projects', 'reflection', 'research', 'security', 'time_calendar'],
      alive: 10,
      elite: 2,
    },
    vector_version: '2.1.0',
  }
}

export function mockAgents(): AgentData[] {
  const districtList = ['coding', 'finance', 'governance', 'health', 'memory_curator', 'projects', 'reflection', 'research', 'security', 'time_calendar']
  const names = ['Nexus', 'Aegis', 'Cipher', 'Vertex', 'Pulse', 'Echo', 'Lumen', 'Stratus', 'Forge', 'Datum', 'Vox', 'Prism']
  const statuses = ['active', 'active', 'active', 'idle', 'active', 'active', 'thinking', 'active', 'idle', 'active', 'active', 'active']
  return names.map((n, i) => ({
    id: `agent-${i}`,
    name: n,
    district: districtList[i % districtList.length],
    health_points: rand(300, 980),
    status: statuses[i],
    is_alive: i < 10,
    model: i % 3 === 0 ? 'gpt-4' : 'claude-3-haiku',
    generation: 1 + Math.floor(i / 4),
  }))
}

export function mockSystemMetrics(): SystemMetrics {
  tick++
  const cpuBase = 35 + Math.sin(tick * 0.1) * 15
  const memBase = 45 + Math.sin(tick * 0.05) * 10
  return {
    cpu_percent: fluctuate(cpuBase, 8),
    memory_percent: fluctuate(memBase, 6),
    memory_used_gb: 12 + Math.sin(tick * 0.1) * 3,
    memory_total_gb: 32,
    disk_percent: fluctuate(62, 3),
    disk_used_gb: 350,
    disk_total_gb: 512,
    net_sent_mb: 1250 + tick * 0.2,
    net_recv_mb: 3400 + tick * 0.5,
    net_sent_rate_mbs: 2.3 + Math.sin(tick * 0.2) * 1,
    net_recv_rate_mbs: 5.1 + Math.sin(tick * 0.15) * 1.5,
    gpu_percent: fluctuate(55, 12),
    gpu_temp_c: 68 + Math.sin(tick * 0.08) * 5,
    gpu_mem_percent: fluctuate(48, 8),
    uptime_seconds: tick * 5 + 36000,
  }
}

export function mockGoals(): GoalsResponse {
  const hasActions = Math.sin(tick * 0.03) > 0.3
  return {
    immediate_actions: hasActions
      ? [{ action: 'analyze_memory', timestamp: new Date().toISOString() }, { action: 'process_event_queue', timestamp: new Date().toISOString() }]
      : [],
  }
}

const eventTypes = ['chat_message', 'decision_approved', 'observation', 'governance_review', 'action_executed', 'chat_message', 'observation', 'error_retry']
const contents = [
  'Agent Nexus completed memory consolidation across 230 episodes',
  'Council approved governance proposal for resource allocation',
  'Health district reported nominal vitals across all agents',
  'Coding district pushed update to core inference module',
  'Security scan completed — no threats detected in agent network',
  'Memory curator optimized episodic index, 15% retrieval improvement',
  'Reflection cycle started for agent cohort gamma',
  'Research district published analysis on embedding efficiency',
  'Time calendar synced — 3 scheduled events pending',
  'Projects district completed milestone delta-4',
  'Agent Cipher requested additional compute for training pipeline',
  'Finance district logged transaction record for infrastructure costs',
]

export function mockEvents(): MemoryEvent[] {
  const events: MemoryEvent[] = []
  const now = Date.now()
  for (let i = 0; i < 25; i++) {
    const typeIndex = rand(0, eventTypes.length - 1)
    events.push({
      id: `mock-ev-${tick}-${i}`,
      timestamp: new Date(now - i * 12000).toISOString(),
      event_type: eventTypes[typeIndex],
      content: contents[rand(0, contents.length - 1)],
      importance: i < 3 ? 'high' : 'normal',
      source: 'mock',
    })
  }
  return events
}
