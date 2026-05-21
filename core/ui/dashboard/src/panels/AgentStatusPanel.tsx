import { useVectorStore } from '../store/vectorStore'
import { hpColor } from '../lib/api'

export default function AgentStatusPanel() {
  const agents = useVectorStore((s) => s.agents)

  return (
    <div style={{ padding: 8 }}>
      <div style={{ fontSize: 9, color: '#1a6688', marginBottom: 8, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
        Agents · {agents.length} total
      </div>
      {agents.length === 0 ? (
        <div style={{ fontSize: 10, color: '#335566', padding: 12, textAlign: 'center' }}>
          No agent data
        </div>
      ) : (
        agents.map((a) => {
          const color = hpColor(a.health_points)
          const pct = Math.min(100, (a.health_points / 1000) * 100)
          return (
            <div
              key={a.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '4px 0',
                borderBottom: '1px solid rgba(0,212,255,0.04)',
                fontSize: 10,
              }}
            >
              <div
                style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: a.is_alive ? color : '#333',
                  boxShadow: `0 0 4px ${color}`,
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: '#aabbcc' }}>
                  <span>{a.name}</span>
                  <span style={{ color, fontSize: 9 }}>{a.health_points} HP</span>
                </div>
                <div style={{ fontSize: 8, color: '#445566' }}>{a.district}</div>
                <div style={{
                  marginTop: 2, height: 3, background: 'rgba(0,212,255,0.08)',
                  borderRadius: 2, overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${pct}%`, height: '100%',
                    background: color,
                    transition: 'width 0.5s ease',
                    borderRadius: 2,
                  }} />
                </div>
              </div>
              <span style={{
                fontSize: 8, color: a.status === 'active' ? '#44FF88' : '#888',
                textTransform: 'uppercase',
              }}>
                {a.status}
              </span>
            </div>
          )
        })
      )}
    </div>
  )
}
