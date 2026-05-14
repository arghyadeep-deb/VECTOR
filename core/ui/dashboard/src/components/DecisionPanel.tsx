import { useMemo } from 'react'
import FloatingPanel from './FloatingPanel'
import { Z } from '../lib/zIndex'
import { useVectorStore } from '../store/vectorStore'

function useScores() {
  const agents = useVectorStore((s) => s.agents)
  const m = useVectorStore((s) => s.systemMetrics)
  const alive = agents.filter((a) => a.is_alive).length
  const total = agents.length
  const hpTotal = agents.reduce((s, a) => s + (a.health_points || 0), 0)
  return useMemo(() => [
    { label: 'System Load', value: Math.round((m?.cpu_percent ?? 0) / 2), color: '#00CFFF' },
    { label: 'Memory Pressure', value: Math.round((m?.memory_percent ?? 0) / 2.5), color: '#00CFFF' },
    { label: 'Agent Vitality', value: Math.round(Math.min(100, (hpTotal / (total || 1)) / 10)), color: '#00CFFF' },
    { label: 'Alive Ratio', value: Math.round((alive / (total || 1)) * 100), color: '#00CFFF' },
  ], [m?.cpu_percent, m?.memory_percent, hpTotal, total, alive])
}

function useCandidates() {
  const goals = useVectorStore((s) => s.goals)
  const agents = useVectorStore((s) => s.agents)
  const m = useVectorStore((s) => s.systemMetrics)
  return useMemo(() => {
    const actions = (goals?.immediate_actions ?? []).slice(0, 5)
    if (actions.length === 0) {
      const atRisk = agents.filter((a) => a.is_alive && (a.health_points || 0) < 300)
      if (atRisk.length > 0) {
        const worst = atRisk.sort((a, b) => (a.health_points || 0) - (b.health_points || 0))[0]
        return [
          { name: `Revive ${worst.name} (${worst.health_points} HP)`, score: Math.round(95 - (m?.cpu_percent ?? 0) / 2), winner: true },
          { name: `Scale ${atRisk.length} at-risk agents`, score: 55, winner: false },
        ]
      }
      return [
        { name: 'Routine system maintenance', score: 65, winner: true },
        { name: 'Monitor agent health pool', score: 48, winner: false },
      ]
    }
    return actions.map((a, i) => ({
      name: typeof a === 'object' ? String(a.action || a.content || JSON.stringify(a)).slice(0, 50) : String(a),
      score: Math.round(100 - i * 15 - Math.random() * 10),
      winner: i === 0,
    }))
  }, [goals, agents, m?.cpu_percent])
}

interface DecisionPanelProps {
  onClose: () => void
  zoneStyle?: React.CSSProperties
}

export default function DecisionPanel({ onClose, zoneStyle }: DecisionPanelProps) {
  const scores = useScores()
  const candidates = useCandidates()

  return (
    <FloatingPanel
      title="DECISION ANALYSIS"
      onClose={onClose}
      autoDismiss={8}
      style={{
        ...zoneStyle,
        width: 380,
        zIndex: Z.FLOATING,
      }}
    >
      <div style={{ padding: '8px 12px' }}>
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a4466', letterSpacing: '0.15em', marginBottom: 6 }}>
            SCORING COMPONENTS
          </div>
          {scores.map((s) => (
            <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#7ecfed', letterSpacing: '0.08em', width: 110, flexShrink: 0 }}>
                {s.label}
              </span>
              <div style={{ flex: 1, height: 6, background: 'rgba(0,207,255,0.06)', border: '1px solid rgba(0,207,255,0.08)' }}>
                <div style={{ width: `${s.value}%`, height: '100%', background: `linear-gradient(90deg, rgba(0,207,255,0.2), ${s.color})`, boxShadow: `0 0 6px ${s.color}66`, transition: 'width 0.5s ease' }} />
              </div>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: '#00CFFF', width: 28, textAlign: 'right' }}>
                {s.value}%
              </span>
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 12 }}>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a4466', letterSpacing: '0.15em', marginBottom: 6 }}>
            CANDIDATES
          </div>
          {candidates.map((c) => (
            <div key={c.name} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '4px 8px', marginBottom: 2,
              background: c.winner ? 'rgba(0,207,255,0.06)' : 'transparent',
              border: c.winner ? '1px solid rgba(0,207,255,0.15)' : 'none',
            }}>
              <span style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
                color: c.winner ? '#00CFFF' : '#3388aa',
              }}>
                {c.winner ? '→ ' : '  '}{c.name}
              </span>
              <span style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: c.winner ? '#00CFFF' : '#1a4466',
              }}>
                {c.score}
              </span>
            </div>
          ))}
        </div>

        <div style={{ textAlign: 'center', borderTop: '1px solid rgba(0,207,255,0.05)', paddingTop: 8 }}>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a4466', letterSpacing: '0.15em', marginBottom: 2 }}>
            FINAL SCORE
          </div>
          <div style={{ fontFamily: "'Orbitron', sans-serif', monospace", fontSize: 28, fontWeight: 700, color: '#00CFFF', lineHeight: 1 }}>
            {candidates.find((c) => c.winner)?.score ?? 0}
          </div>
        </div>
      </div>
    </FloatingPanel>
  )
}
