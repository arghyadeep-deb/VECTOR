import { useEffect, useRef, useState } from 'react'

interface Person {
  person_id: string
  name: string
  trust: number
  communication_style: string
  technical_level: string
  interaction_count: number
  last_interaction: string | null
  beliefs: Record<string, { value: unknown; confidence: number }>
  preferences: Record<string, unknown>
}

const trustColor = (t: number) =>
  t >= 0.7 ? '#00ff88' : t >= 0.4 ? '#ffaa00' : '#ff4444'

export default function PersonGraph() {
  const [persons, setPersons] = useState<Person[]>([])
  const [selected, setSelected] = useState<Person | null>(null)
  const [editingBelief, setEditingBelief] = useState<{ key: string; value: string } | null>(null)
  const [editingTrust, setEditingTrust] = useState(false)
  const [trustInput, setTrustInput] = useState('')
  const [error, setError] = useState(false)
  const mountedRef = useRef(true)

  const loadAll = async () => {
    try {
      const r = await fetch('/brain/persons', { cache: 'no-store' })
      if (!r.ok) throw new Error(`${r.status}`)
      const data = await r.json()
      if (mountedRef.current) {
        setPersons(Array.isArray(data) ? data : data.persons ?? [])
        setError(false)
      }
    } catch {
      if (mountedRef.current) setError(true)
    }
  }

  const loadOne = async (id: string) => {
    try {
      const r = await fetch(`/brain/persons/${id}`, { cache: 'no-store' })
      if (!r.ok) return
      const data = await r.json()
      if (mountedRef.current) setSelected(data)
    } catch {}
  }

  const saveBelief = async (key: string, value: string) => {
    if (!selected) return
    try {
      await fetch(`/brain/persons/${selected.person_id}/belief`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value, confidence: 0.9 }),
      })
      await loadOne(selected.person_id)
    } catch {}
    setEditingBelief(null)
  }

  const saveTrust = async (delta: number) => {
    if (!selected) return
    try {
      await fetch(`/brain/persons/${selected.person_id}/trust`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delta }),
      })
      await loadOne(selected.person_id)
      await loadAll()
    } catch {}
    setEditingTrust(false)
  }

  useEffect(() => {
    mountedRef.current = true
    loadAll()
    const id = setInterval(loadAll, 20000)
    return () => { mountedRef.current = false; clearInterval(id) }
  }, [])

  if (error) return (
    <div style={{ padding: 16, color: '#ff4444', fontSize: 12, fontFamily: 'monospace' }}>
      /brain/persons unreachable
    </div>
  )

  if (!persons.length) return (
    <div style={{ padding: 16, color: '#4a6a7a', fontSize: 12, fontFamily: 'monospace' }}>
      No persons in model yet — VECTOR learns them through interactions.
    </div>
  )

  return (
    <div style={{ display: 'flex', height: '100%', gap: 0 }}>
      {/* Card grid */}
      <div style={{
        flex: selected ? '0 0 55%' : '1 1 100%',
        overflowY: 'auto',
        padding: 12,
        display: 'flex',
        flexWrap: 'wrap',
        gap: 10,
        alignContent: 'flex-start',
        transition: 'flex 0.2s',
      }}>
        {persons.map((p) => {
          const color = trustColor(p.trust)
          const isActive = selected?.person_id === p.person_id
          return (
            <div
              key={p.person_id}
              onClick={() => { setSelected(p); loadOne(p.person_id) }}
              style={{
                width: 'calc(50% - 5px)',
                background: isActive ? 'rgba(0,207,255,0.08)' : 'rgba(0,20,35,0.7)',
                border: `1px solid ${isActive ? '#00cfff66' : color + '33'}`,
                borderLeft: `3px solid ${color}`,
                borderRadius: 5,
                padding: '10px 12px',
                cursor: 'pointer',
                transition: 'background 0.15s, border 0.15s',
              }}
            >
              <div style={{ color: '#e0f0f8', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                {p.name}
              </div>
              {/* Trust bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <div style={{ flex: 1, height: 3, background: '#0a1a28', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ width: `${p.trust * 100}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.3s' }} />
                </div>
                <span style={{ color, fontSize: 10, fontFamily: 'monospace' }}>{(p.trust * 100).toFixed(0)}%</span>
              </div>
              <div style={{ color: '#4a6a7a', fontSize: 10, fontFamily: 'monospace' }}>
                {p.communication_style} · {p.technical_level} · {p.interaction_count} interactions
              </div>
              {p.last_interaction && (
                <div style={{ color: '#3a5a6a', fontSize: 10, marginTop: 3 }}>
                  last: {new Date(p.last_interaction).toLocaleDateString()}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Side panel */}
      {selected && (
        <div style={{
          flex: '0 0 45%',
          borderLeft: '1px solid #0a2535',
          background: 'rgba(0,10,20,0.85)',
          overflowY: 'auto',
          padding: 14,
        }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <div style={{ color: '#e0f0f8', fontSize: 14, fontWeight: 600 }}>{selected.name}</div>
              <div style={{ color: '#4a6a7a', fontSize: 10, fontFamily: 'monospace' }}>{selected.person_id}</div>
            </div>
            <button
              onClick={() => setSelected(null)}
              style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#4a6a7a', cursor: 'pointer', fontSize: 16 }}
            >×</button>
          </div>

          {/* Trust section */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ color: '#4a6a7a', fontSize: 10, fontFamily: 'monospace', marginBottom: 6, letterSpacing: 1 }}>TRUST SCORE</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ flex: 1, height: 6, background: '#0a1a28', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{
                  width: `${selected.trust * 100}%`,
                  height: '100%',
                  background: trustColor(selected.trust),
                  borderRadius: 3,
                  transition: 'width 0.3s',
                }} />
              </div>
              <span style={{ color: trustColor(selected.trust), fontSize: 12, fontFamily: 'monospace', minWidth: 36 }}>
                {(selected.trust * 100).toFixed(0)}%
              </span>
              {!editingTrust ? (
                <button onClick={() => { setEditingTrust(true); setTrustInput('') }} style={{
                  background: '#0a2535', border: '1px solid #1a4555', color: '#00cfff',
                  borderRadius: 3, padding: '2px 8px', fontSize: 10, cursor: 'pointer',
                }}>adjust</button>
              ) : (
                <div style={{ display: 'flex', gap: 4 }}>
                  <input
                    autoFocus
                    value={trustInput}
                    onChange={e => setTrustInput(e.target.value)}
                    placeholder="±0.1"
                    style={{
                      width: 52, background: '#071520', border: '1px solid #1a4555',
                      color: '#e0f0f8', borderRadius: 3, padding: '2px 6px', fontSize: 11,
                    }}
                  />
                  <button onClick={() => saveTrust(parseFloat(trustInput) || 0)} style={{
                    background: '#00ff8822', border: '1px solid #00ff8855', color: '#00ff88',
                    borderRadius: 3, padding: '2px 6px', fontSize: 10, cursor: 'pointer',
                  }}>✓</button>
                  <button onClick={() => setEditingTrust(false)} style={{
                    background: 'none', border: 'none', color: '#4a6a7a', cursor: 'pointer', fontSize: 14,
                  }}>×</button>
                </div>
              )}
            </div>
          </div>

          {/* Beliefs */}
          <div>
            <div style={{ color: '#4a6a7a', fontSize: 10, fontFamily: 'monospace', marginBottom: 6, letterSpacing: 1 }}>BELIEFS</div>
            {Object.keys(selected.beliefs ?? {}).length === 0 && (
              <div style={{ color: '#3a5a6a', fontSize: 11 }}>No beliefs recorded yet.</div>
            )}
            {Object.entries(selected.beliefs ?? {}).map(([key, belief]) => {
              const isEditing = editingBelief?.key === key
              return (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '5px 0', borderBottom: '1px solid #0a1a28',
                }}>
                  <span style={{ color: '#7aabbc', fontSize: 11, fontFamily: 'monospace', minWidth: 80, flexShrink: 0 }}>{key}</span>
                  {isEditing ? (
                    <>
                      <input
                        autoFocus
                        value={editingBelief.value}
                        onChange={e => setEditingBelief({ key, value: e.target.value })}
                        style={{
                          flex: 1, background: '#071520', border: '1px solid #1a4555',
                          color: '#e0f0f8', borderRadius: 3, padding: '2px 6px', fontSize: 11,
                        }}
                      />
                      <button onClick={() => saveBelief(key, editingBelief.value)} style={{
                        background: '#00ff8822', border: '1px solid #00ff8855', color: '#00ff88',
                        borderRadius: 3, padding: '2px 5px', fontSize: 10, cursor: 'pointer',
                      }}>✓</button>
                      <button onClick={() => setEditingBelief(null)} style={{
                        background: 'none', border: 'none', color: '#4a6a7a', cursor: 'pointer', fontSize: 14,
                      }}>×</button>
                    </>
                  ) : (
                    <>
                      <span style={{ flex: 1, color: '#c0d8e8', fontSize: 11 }}>
                        {String(belief.value ?? '')}
                      </span>
                      <span style={{ color: '#3a5a6a', fontSize: 10, fontFamily: 'monospace' }}>
                        {(belief.confidence * 100).toFixed(0)}%
                      </span>
                      <button onClick={() => setEditingBelief({ key, value: String(belief.value ?? '') })} style={{
                        background: 'none', border: 'none', color: '#4a6a7a', cursor: 'pointer', fontSize: 11, padding: '0 2px',
                      }}>✎</button>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
