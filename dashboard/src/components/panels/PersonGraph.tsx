import { useState, useEffect, useCallback } from 'react'

interface Person {
  person_id: string
  name: string
  trust: number
  interaction_count: number
  beliefs?: Record<string, unknown>
  preferences?: Record<string, unknown>
  relationship?: string
}

interface PersonDetail {
  person: Person
  interaction_history: Array<{ summary: string; ts: string }>
}

const GRAPH_W = 240
const GRAPH_H = 200
const TRUST_TO_COLOR = (t: number) =>
  t >= 0.8 ? '#30FF6A' : t >= 0.5 ? '#FFB800' : '#FF3B30'

function nodeRadius(trust: number, interactions: number): number {
  return Math.max(6, Math.min(18, 6 + trust * 6 + Math.log(interactions + 1)))
}

function placeNodes(persons: Person[]): Array<{ x: number; y: number; p: Person }> {
  const cx = GRAPH_W / 2
  const cy = GRAPH_H / 2
  if (persons.length === 0) return []
  if (persons.length === 1) return [{ x: cx, y: cy, p: persons[0] }]
  const r = Math.min(cx, cy) * 0.7
  return persons.map((p, i) => {
    const angle = (i / persons.length) * 2 * Math.PI - Math.PI / 2
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle), p }
  })
}

function SidePanelContent({
  detail,
  onUpdateBelief,
  onUpdateTrust,
}: {
  detail: PersonDetail
  onUpdateBelief: (key: string, value: string) => void
  onUpdateTrust: (delta: number) => void
}) {
  const { person } = detail
  const [newBeliefKey, setNewBeliefKey] = useState('')
  const [newBeliefVal, setNewBeliefVal] = useState('')

  return (
    <div style={{ fontSize: '0.6rem', color: 'var(--jarvis-text)', lineHeight: 1.6 }}>
      <div style={{ marginBottom: 8 }}>
        <span style={{ color: 'var(--jarvis-cyan)', fontWeight: 600 }}>{person.name}</span>
        <span style={{ color: 'var(--jarvis-text-dim)', marginLeft: 8 }}>
          {person.relationship ?? 'unknown'}
        </span>
      </div>

      {/* Trust bar */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
          <span className="label">TRUST</span>
          <span style={{ color: TRUST_TO_COLOR(person.trust) }}>{(person.trust * 100).toFixed(0)}%</span>
        </div>
        <div style={{ height: 3, background: 'var(--jarvis-border)', borderRadius: 2, marginBottom: 4 }}>
          <div style={{
            height: '100%', borderRadius: 2, width: `${person.trust * 100}%`,
            background: TRUST_TO_COLOR(person.trust),
            transition: 'width 0.4s',
          }} />
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <button onClick={() => onUpdateTrust(0.05)}
            style={{ flex: 1, padding: '2px 0', fontSize: '0.55rem', cursor: 'pointer',
                     background: 'rgba(48,255,106,0.1)', border: '1px solid #30FF6A',
                     color: '#30FF6A', borderRadius: 2 }}>
            +5%
          </button>
          <button onClick={() => onUpdateTrust(-0.05)}
            style={{ flex: 1, padding: '2px 0', fontSize: '0.55rem', cursor: 'pointer',
                     background: 'rgba(255,59,48,0.1)', border: '1px solid #FF3B30',
                     color: '#FF3B30', borderRadius: 2 }}>
            -5%
          </button>
        </div>
      </div>

      {/* Beliefs */}
      {person.beliefs && Object.keys(person.beliefs).length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div className="label" style={{ marginBottom: 3 }}>BELIEFS</div>
          {Object.entries(person.beliefs).slice(0, 5).map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0',
                                   borderBottom: '1px solid rgba(10,48,80,0.5)' }}>
              <span style={{ color: 'var(--jarvis-text-dim)' }}>{k}</span>
              <span style={{ color: 'var(--jarvis-text)', maxWidth: 100, textAlign: 'right',
                             overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {String(v)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Add belief */}
      <div style={{ marginBottom: 8 }}>
        <div className="label" style={{ marginBottom: 3 }}>ADD BELIEF</div>
        <input placeholder="key" value={newBeliefKey} onChange={e => setNewBeliefKey(e.target.value)}
          style={{ width: '100%', marginBottom: 3, padding: '2px 4px', fontSize: '0.55rem',
                   background: 'rgba(0,212,255,0.05)', border: '1px solid var(--jarvis-border)',
                   color: 'var(--jarvis-text)', borderRadius: 2 }} />
        <input placeholder="value" value={newBeliefVal} onChange={e => setNewBeliefVal(e.target.value)}
          style={{ width: '100%', marginBottom: 3, padding: '2px 4px', fontSize: '0.55rem',
                   background: 'rgba(0,212,255,0.05)', border: '1px solid var(--jarvis-border)',
                   color: 'var(--jarvis-text)', borderRadius: 2 }} />
        <button onClick={() => { onUpdateBelief(newBeliefKey, newBeliefVal); setNewBeliefKey(''); setNewBeliefVal('') }}
          disabled={!newBeliefKey.trim()}
          style={{ width: '100%', padding: '3px 0', fontSize: '0.55rem', cursor: 'pointer',
                   background: 'rgba(0,212,255,0.1)', border: '1px solid var(--jarvis-cyan)',
                   color: 'var(--jarvis-cyan)', borderRadius: 2 }}>
          SAVE
        </button>
      </div>

      {/* Interaction count */}
      <div style={{ color: 'var(--jarvis-text-dim)' }}>
        {person.interaction_count} interaction{person.interaction_count !== 1 ? 's' : ''} recorded
      </div>
    </div>
  )
}

export function PersonGraph() {
  const [persons, setPersons] = useState<Person[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<PersonDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchPersons = useCallback(async () => {
    try {
      const r = await fetch('/brain/persons')
      if (!r.ok) return
      const body = await r.json()
      setPersons(body.persons ?? [])
    } catch { /* offline */ }
  }, [])

  useEffect(() => {
    fetchPersons()
    const timer = setInterval(fetchPersons, 30000)
    return () => clearInterval(timer)
  }, [fetchPersons])

  const selectPerson = async (id: string) => {
    if (selected === id) { setSelected(null); setDetail(null); return }
    setSelected(id)
    setLoading(true)
    try {
      const r = await fetch(`/brain/persons/${encodeURIComponent(id)}`)
      if (r.ok) setDetail(await r.json())
    } catch { setError('Failed to load person') }
    setLoading(false)
  }

  const handleUpdateBelief = async (key: string, value: string) => {
    if (!selected || !key.trim()) return
    try {
      await fetch(`/brain/persons/${encodeURIComponent(selected)}/belief`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value }),
      })
      await selectPerson(selected)
    } catch { setError('Belief update failed') }
  }

  const handleUpdateTrust = async (delta: number) => {
    if (!selected) return
    try {
      await fetch(`/brain/persons/${encodeURIComponent(selected)}/trust`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delta }),
      })
      await fetchPersons()
      if (selected) await selectPerson(selected)
    } catch { setError('Trust update failed') }
  }

  const nodes = placeNodes(persons)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="label" style={{ marginBottom: 4 }}>
        PERSON GRAPH — {persons.length} KNOWN
      </div>

      {error && (
        <div style={{ fontSize: '0.6rem', color: '#FF3B30', marginBottom: 4 }}>{error}</div>
      )}

      {persons.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: 'var(--jarvis-text-dim)', fontSize: '0.65rem' }}>
          No persons in model yet
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 4, flex: 1, minHeight: 0 }}>
          {/* SVG force graph */}
          <svg width={GRAPH_W} height={GRAPH_H}
               style={{ flex: '0 0 auto', background: 'rgba(0,212,255,0.03)',
                        border: '1px solid var(--jarvis-border)', borderRadius: 2 }}>
            {/* Center hub */}
            <circle cx={GRAPH_W / 2} cy={GRAPH_H / 2} r={5}
                    fill="none" stroke="var(--jarvis-cyan)" strokeWidth={1}
                    strokeDasharray="3 2" />

            {/* Edges */}
            {nodes.map(({ x, y, p }) => (
              <line key={`e-${p.person_id}`}
                    x1={GRAPH_W / 2} y1={GRAPH_H / 2} x2={x} y2={y}
                    stroke={TRUST_TO_COLOR(p.trust)} strokeWidth={0.5} strokeOpacity={0.4} />
            ))}

            {/* Nodes */}
            {nodes.map(({ x, y, p }) => {
              const r = nodeRadius(p.trust, p.interaction_count ?? 0)
              const color = TRUST_TO_COLOR(p.trust)
              const isSelected = selected === p.person_id
              return (
                <g key={p.person_id} onClick={() => selectPerson(p.person_id)}
                   style={{ cursor: 'pointer' }}>
                  <circle cx={x} cy={y} r={r + (isSelected ? 3 : 0)}
                          fill={isSelected ? `${color}22` : 'rgba(0,0,0,0)'}
                          stroke={color} strokeWidth={isSelected ? 1.5 : 1}
                          style={{ filter: isSelected ? `drop-shadow(0 0 4px ${color})` : 'none' }} />
                  <text x={x} y={y + r + 9} textAnchor="middle"
                        fontSize={8} fill="var(--jarvis-text-dim)" style={{ pointerEvents: 'none' }}>
                    {p.name.slice(0, 10)}
                  </text>
                </g>
              )
            })}
          </svg>

          {/* Side panel */}
          <div style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '4px 0' }}>
            {loading && (
              <div style={{ fontSize: '0.6rem', color: 'var(--jarvis-text-dim)' }}>Loading...</div>
            )}
            {!loading && detail && (
              <SidePanelContent
                detail={detail}
                onUpdateBelief={handleUpdateBelief}
                onUpdateTrust={handleUpdateTrust}
              />
            )}
            {!loading && !detail && selected && (
              <div style={{ fontSize: '0.6rem', color: 'var(--jarvis-text-dim)' }}>
                Click a node to inspect
              </div>
            )}
            {!loading && !selected && (
              <div style={{ fontSize: '0.6rem', color: 'var(--jarvis-text-dim)' }}>
                Click a person node to inspect
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
