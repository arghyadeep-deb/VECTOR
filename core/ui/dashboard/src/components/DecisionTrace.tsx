import { useEffect, useRef, useState } from 'react'

interface ReasoningChain {
  id: string
  situation: string
  steps: string[]
  action_taken: string
  outcome: string | null
  reward: number
  created_at: string
}

const tierColor = (reward: number) =>
  reward >= 0.7 ? '#00ff88' : reward >= 0.4 ? '#ffaa00' : '#ff4444'

const tierLabel = (reward: number) =>
  reward >= 0.7 ? 'GREEN' : reward >= 0.4 ? 'YELLOW' : 'RED'

export default function DecisionTrace() {
  const [chains, setChains] = useState<ReasoningChain[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const mountedRef = useRef(true)

  const load = async () => {
    try {
      const r = await fetch('/brain/reasoning/chains?limit=20', { cache: 'no-store' })
      if (!r.ok) throw new Error(`${r.status}`)
      const data = await r.json()
      if (mountedRef.current) {
        setChains(Array.isArray(data) ? data : data.chains ?? [])
        setError(false)
      }
    } catch {
      if (mountedRef.current) setError(true)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    load()
    // Poll every 15s; also refreshes on DECISION_MADE ws events via DataPoller
    const id = setInterval(load, 15000)
    return () => { mountedRef.current = false; clearInterval(id) }
  }, [])

  if (error) return (
    <div style={{ padding: 16, color: '#ff4444', fontSize: 12, fontFamily: 'monospace' }}>
      /brain/reasoning/chains unreachable
    </div>
  )

  if (!chains.length) return (
    <div style={{ padding: 16, color: '#4a6a7a', fontSize: 12, fontFamily: 'monospace' }}>
      No reasoning chains yet — waiting for decisions…
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 12px', overflowY: 'auto', maxHeight: '100%' }}>
      {chains.map((chain) => {
        const color = tierColor(chain.reward)
        const isOpen = expanded === chain.id
        const ts = chain.created_at ? new Date(chain.created_at).toLocaleTimeString('en-US', { hour12: false }) : '—'
        return (
          <div
            key={chain.id}
            onClick={() => setExpanded(isOpen ? null : chain.id)}
            style={{
              background: 'rgba(0,20,35,0.7)',
              border: `1px solid ${color}33`,
              borderLeft: `3px solid ${color}`,
              borderRadius: 4,
              padding: '8px 10px',
              cursor: 'pointer',
              transition: 'background 0.15s',
            }}
          >
            {/* Header row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: isOpen ? 8 : 0 }}>
              <span style={{
                background: color + '22',
                color,
                border: `1px solid ${color}55`,
                borderRadius: 3,
                padding: '1px 5px',
                fontSize: 10,
                fontFamily: 'monospace',
                letterSpacing: 1,
                flexShrink: 0,
              }}>
                {tierLabel(chain.reward)}
              </span>
              <span style={{ color: '#00cfff', fontSize: 11, fontFamily: 'monospace', flexShrink: 0 }}>
                {ts}
              </span>
              <span style={{ color: '#c0d8e8', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {chain.action_taken || chain.situation}
              </span>
              <span style={{ marginLeft: 'auto', color: color, fontSize: 11, flexShrink: 0 }}>
                {(chain.reward * 100).toFixed(0)}%
              </span>
            </div>

            {/* Expanded detail */}
            {isOpen && (
              <div style={{ paddingLeft: 8, borderLeft: '1px solid #1a3a4a' }}>
                {chain.situation && (
                  <div style={{ color: '#7aabbc', fontSize: 11, marginBottom: 6, fontFamily: 'monospace' }}>
                    <span style={{ color: '#4a6a7a' }}>situation: </span>{chain.situation}
                  </div>
                )}
                {chain.steps?.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <div style={{ color: '#4a6a7a', fontSize: 10, fontFamily: 'monospace', marginBottom: 3 }}>REASONING STEPS</div>
                    {chain.steps.map((step, i) => (
                      <div key={i} style={{ display: 'flex', gap: 6, marginBottom: 2 }}>
                        <span style={{ color: '#4a6a7a', fontSize: 10, flexShrink: 0 }}>{i + 1}.</span>
                        <span style={{ color: '#a0c4d4', fontSize: 11 }}>{step}</span>
                      </div>
                    ))}
                  </div>
                )}
                {chain.outcome && (
                  <div style={{ color: '#7aabbc', fontSize: 11, fontFamily: 'monospace' }}>
                    <span style={{ color: '#4a6a7a' }}>outcome: </span>{chain.outcome}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
