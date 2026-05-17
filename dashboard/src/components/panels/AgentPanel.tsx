interface Props { activeAgents: number }

const AGENTS = [
  { name: 'Orchestrator', district: 'governance', hp: 850, status: 'active' },
  { name: 'Researcher', district: 'research', hp: 720, status: 'idle' },
  { name: 'Archivist', district: 'memory', hp: 910, status: 'active' },
  { name: 'Code Executor', district: 'coding', hp: 780, status: 'idle' },
  { name: 'Critic', district: 'coding', hp: 650, status: 'idle' },
  { name: 'Planner', district: 'governance', hp: 800, status: 'idle' },
  { name: 'Morning Brief', district: 'intelligence', hp: 870, status: 'idle' },
  { name: 'ThreatScout', district: 'security', hp: 920, status: 'active' },
]

const HP_COLOR = (hp: number) =>
  hp > 800 ? '#30FF6A' : hp > 600 ? '#FFB800' : '#FF3B30'

export function AgentPanel({ activeAgents }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div className="label" style={{ marginBottom: 4 }}>
        ACTIVE: <span style={{ color: '#30FF6A' }}>{activeAgents}</span> / {AGENTS.length}
      </div>
      {AGENTS.map((agent) => (
        <div key={agent.name} style={{
          padding: '6px 8px',
          background: agent.status === 'active' ? 'rgba(0,212,255,0.05)' : 'transparent',
          border: '1px solid',
          borderColor: agent.status === 'active' ? 'rgba(0,212,255,0.2)' : 'var(--jarvis-border)',
          borderRadius: 2,
          display: 'flex', flexDirection: 'column', gap: 3,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--jarvis-text)' }}>{agent.name}</span>
            <span style={{ fontSize: '0.6rem', color: HP_COLOR(agent.hp) }}>{agent.hp} HP</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '0.6rem', color: 'var(--jarvis-text-dim)' }}>#{agent.district}</span>
            <span style={{
              fontSize: '0.55rem', letterSpacing: '0.1em',
              color: agent.status === 'active' ? '#30FF6A' : 'var(--jarvis-text-muted)',
            }}>{agent.status.toUpperCase()}</span>
          </div>
          {/* HP bar */}
          <div style={{ height: 2, background: 'var(--jarvis-border)', borderRadius: 1 }}>
            <div style={{
              height: '100%', borderRadius: 1,
              width: `${agent.hp / 10}%`,
              background: HP_COLOR(agent.hp),
              boxShadow: `0 0 4px ${HP_COLOR(agent.hp)}`,
              transition: 'width 0.5s',
            }} />
          </div>
        </div>
      ))}
    </div>
  )
}
