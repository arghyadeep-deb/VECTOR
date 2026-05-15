import { useMemo } from 'react'
import { useVectorStore } from '../store/vectorStore'
import FloatingPanel from './FloatingPanel'

function hpColor(hp: number): string {
  const t = Math.min(1000, Math.max(0, hp))
  if (t <= 500) {
    const f = t / 500
    const r = 255
    const g = Math.round(51 + (179 - 51) * f)
    const b = Math.round(51 + (0 - 51) * f)
    return `rgb(${r},${g},${b})`
  }
  const f = (t - 500) / 500
  const r = Math.round(255 + (0 - 255) * f)
  const g = Math.round(179 + (207 - 179) * f)
  const b = Math.round(0 + (255 - 0) * f)
  return `rgb(${r},${g},${b})`
}

function statusBadge(status: string, isAlive: boolean): { text: string; color: string } {
  if (status === 'council' || status === 'governance') return { text: 'COUNCIL', color: '#42A5F5' }
  if (!isAlive) return { text: 'DEAD', color: '#ff3355' }
  return { text: 'ACTIVE', color: '#4FC3F7' }
}

function HPHistorySparkline({ history }: { history: number[] }) {
  const w = 80; const h = 20; const max = 1000
  const pts = history.map((v, i) => [(i / (history.length - 1)) * w, h - (v / max) * h] as [number, number])
  const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0]} ${p[1]}`).join(' ')
  return (
    <svg width={w} height={h}>
      <path d={d} fill="none" stroke="#4FC3F7" strokeWidth={1} opacity={0.4} />
      {pts.length > 0 && <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r={1.5} fill="#4FC3F7" />}
    </svg>
  )
}

function generateHPHistory(): number[] {
  const arr: number[] = []
  let hp = 500 + Math.random() * 300
  for (let i = 0; i < 24; i++) { hp += (Math.random() - 0.5) * 100; hp = Math.max(50, Math.min(1000, hp)); arr.push(Math.round(hp)) }
  return arr
}

interface DistrictDetailProps {
  district: string
  onClose: () => void
  zoneStyle?: React.CSSProperties
}

export default function DistrictDetail({ district, onClose, zoneStyle }: DistrictDetailProps) {
  const rawAgents = useVectorStore((s) => s.agents).filter((a) => a.district === district)
  // Deduplicate by id — registry can return duplicates if bootstrap runs twice
  const seen = new Set<string>()
  const agents = rawAgents.filter((a) => {
    const key = a.id || a.name
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
  const history = useMemo(() => generateHPHistory(), [])

  return (
    <FloatingPanel
      title={district.toUpperCase()}
      subtitle={`${agents.length} units`}
      onClose={onClose}
      style={{
        ...zoneStyle,
        width: 300,
      }}
    >
      <div style={{ padding: '4px 0' }}>
        {agents.length === 0 ? (
          <div style={{ padding: '12px', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#1a4466', textAlign: 'center' }}>No agents found for this district</div>
        ) : (
          agents.map((agent) => {
            const badge = statusBadge(agent.status, agent.is_alive)
            const color = hpColor(agent.health_points)
            return (
              <div key={agent.id} style={{ padding: '6px 12px', borderBottom: '1px solid rgba(0,207,255,0.03)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#7ecfed', letterSpacing: '0.08em' }}>{agent.name || agent.id}</span>
                  <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: badge.color, border: `1px solid ${badge.color}44`, padding: '1px 5px', letterSpacing: '0.1em' }}>{badge.text}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ flex: 1, height: 4, background: 'rgba(0,207,255,0.06)', border: '1px solid rgba(0,207,255,0.08)' }}>
                    <div style={{ width: `${(agent.health_points / 1000) * 100}%`, height: '100%', background: color, boxShadow: `0 0 4px ${color}`, transition: 'width 0.5s ease' }} />
                  </div>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color, width: 35, textAlign: 'right' }}>{agent.health_points}</span>
                </div>
              </div>
            )
          })
        )}
        <div style={{ padding: '8px 12px', borderTop: '1px solid rgba(0,207,255,0.05)' }}>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a4466', letterSpacing: '0.15em', marginBottom: 4 }}>HP HISTORY (24h)</div>
          <HPHistorySparkline history={history} />
        </div>
      </div>
    </FloatingPanel>
  )
}
