import { VectorState } from '../../App'

interface Props { state: VectorState }

function Gauge({ label, value, max = 100, unit = '%', color = '#00D4FF' }: {
  label: string; value: number; max?: number; unit?: string; color?: string
}) {
  const pct = Math.min((value / max) * 100, 100)
  const c = pct > 80 ? '#FF3B30' : pct > 60 ? '#FFB800' : color
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span className="label">{label}</span>
        <span style={{ fontSize: '0.7rem', color: c }}>{value}{unit}</span>
      </div>
      <div style={{ height: 3, background: 'var(--jarvis-border)', borderRadius: 2 }}>
        <div style={{
          height: '100%', borderRadius: 2, width: `${pct}%`,
          background: c, boxShadow: `0 0 6px ${c}`,
          transition: 'width 0.5s, background 0.3s',
        }} />
      </div>
    </div>
  )
}

export function SystemMetrics({ state }: Props) {
  return (
    <div>
      <Gauge label="Memory" value={state.memoryUsage} unit="%" />
      <Gauge label="Active Tasks" value={state.totalTasks} max={20} unit="" />
      <Gauge label="Agents" value={state.activeAgents} max={133} unit="" color="#1A8FFF" />

      <div style={{ marginTop: 12, marginBottom: 8, borderTop: '1px solid var(--jarvis-border)', paddingTop: 8 }}>
        <span className="label">Districts Online</span>
      </div>

      {[
        { name: 'governance', online: true },
        { name: 'security', online: true },
        { name: 'coding', online: true },
        { name: 'research', online: true },
        { name: 'communications', online: true },
        { name: 'memory_curator', online: true },
        { name: 'intelligence', online: true },
        { name: 'time_calendar', online: true },
      ].map(d => (
        <div key={d.name} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '3px 0', borderBottom: '1px solid rgba(10,48,80,0.5)',
        }}>
          <span style={{ fontSize: '0.65rem', color: 'var(--jarvis-text-dim)' }}>
            {d.name.replace('_', ' ').toUpperCase()}
          </span>
          <span style={{ fontSize: '0.55rem', color: d.online ? '#30FF6A' : '#FF3B30' }}>
            {d.online ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
      ))}

      <div style={{ marginTop: 12 }}>
        <div className="label" style={{ marginBottom: 4 }}>Last Action</div>
        <div style={{
          fontSize: '0.65rem', color: 'var(--jarvis-text)',
          padding: '6px 8px',
          background: 'rgba(0,212,255,0.04)',
          border: '1px solid var(--jarvis-border)',
          borderRadius: 2,
          lineHeight: 1.4,
          wordBreak: 'break-word',
        }}>
          {state.lastAction || 'Awaiting input...'}
        </div>
      </div>
    </div>
  )
}
