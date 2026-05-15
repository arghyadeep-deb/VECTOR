import { useState, useEffect } from 'react'

interface Claim {
  id: string
  issue_id: string
  title: string
  status: string
  progress: number
  agent: string
  priority: string
}

const STATUS_COLORS: Record<string, string> = {
  active: '#4FC3F7',
  stealable: '#FFB300',
  blocked: '#EF5350',
  paused: '#78909C',
  pending_handoff: '#AB47BC',
  in_review: '#66BB6A',
  completed: '#26A69A',
}

const PRIORITY_DOT: Record<string, string> = {
  critical: '#EF5350',
  high: '#FF7043',
  medium: '#FFA726',
  low: '#78909C',
}

const MOCK_CLAIMS: Claim[] = [
  { id: 'claim-001', issue_id: 'TASK-001', title: 'Fix auth token expiry', status: 'active', progress: 65, agent: 'vector-coder', priority: 'high' },
  { id: 'claim-002', issue_id: 'TASK-002', title: 'Research LightRAG patterns', status: 'stealable', progress: 12, agent: 'vector-researcher', priority: 'medium' },
  { id: 'claim-003', issue_id: 'TASK-003', title: 'Review security policy', status: 'in_review', progress: 100, agent: 'vector-security', priority: 'critical' },
]

export default function ClaimsBoard() {
  const [claims, setClaims] = useState<Claim[]>(MOCK_CLAIMS)
  const [lastUpdate, setLastUpdate] = useState<string>('')
  const [error, setError] = useState(false)

  useEffect(() => {
    const fetch_claims = async () => {
      try {
        const r = await fetch('/claims', { cache: 'no-store' })
        if (!r.ok) throw new Error()
        const d = await r.json()
        setClaims(d.claims ?? MOCK_CLAIMS)
        setError(false)
      } catch {
        setError(true)
      }
      setLastUpdate(new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    }
    fetch_claims()
    const id = setInterval(fetch_claims, 10_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{
      background: 'rgba(0,8,20,0.88)',
      border: '1px solid rgba(79,195,247,0.25)',
      borderRadius: 6,
      padding: '8px 10px',
      fontFamily: 'monospace',
      fontSize: 11,
      color: '#B0BEC5',
      minWidth: 200,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ color: '#4FC3F7', fontWeight: 700, fontSize: 10, letterSpacing: 1.5 }}>
          CLAIMS BOARD
        </span>
        <span style={{ color: error ? '#EF5350' : '#546E7A', fontSize: 9 }}>
          {error ? 'MOCK' : lastUpdate}
        </span>
      </div>

      {/* Claim rows */}
      {claims.length === 0 && (
        <div style={{ color: '#37474F', fontSize: 10, textAlign: 'center', padding: '8px 0' }}>no active claims</div>
      )}
      {claims.map(c => (
        <div key={c.id} style={{
          marginBottom: 5,
          padding: '4px 6px',
          background: c.status === 'stealable' ? 'rgba(255,179,0,0.06)' : 'rgba(255,255,255,0.02)',
          borderRadius: 4,
          borderLeft: `2px solid ${STATUS_COLORS[c.status] ?? '#37474F'}`,
        }}>
          {/* Title row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#CFD8DC', fontSize: 10, maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span style={{ color: PRIORITY_DOT[c.priority] ?? '#546E7A', marginRight: 3 }}>•</span>
              {c.title}
            </span>
            <span style={{
              color: STATUS_COLORS[c.status] ?? '#546E7A',
              fontSize: 8,
              letterSpacing: 0.8,
              textTransform: 'uppercase',
            }}>
              {c.status.replace('_', ' ')}
            </span>
          </div>

          {/* Progress + agent */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 3 }}>
            <div style={{ flex: 1, height: 2, background: 'rgba(255,255,255,0.08)', borderRadius: 1 }}>
              <div style={{ width: `${c.progress}%`, height: '100%', background: STATUS_COLORS[c.status] ?? '#4FC3F7', borderRadius: 1, transition: 'width 0.4s' }} />
            </div>
            <span style={{ color: '#546E7A', fontSize: 9, minWidth: 22, textAlign: 'right' }}>{c.progress}%</span>
            <span style={{ color: '#37474F', fontSize: 8 }}>{c.agent.replace('vector-', '')}</span>
          </div>
        </div>
      ))}

      {/* Footer */}
      <div style={{ marginTop: 4, color: '#37474F', fontSize: 9, display: 'flex', justifyContent: 'space-between' }}>
        <span>{claims.filter(c => c.status === 'active').length} active</span>
        <span style={{ color: '#FFB300' }}>{claims.filter(c => c.status === 'stealable').length} stealable</span>
      </div>
    </div>
  )
}
