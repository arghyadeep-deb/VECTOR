import { useState, useEffect } from 'react'

export interface DecisionEvent {
  id: string
  action_type: string
  score: number
  goal_ids: string[]
  ts: number
  tier?: 'GREEN' | 'YELLOW' | 'RED'
  outcome?: string
}

interface ReasoningChain {
  id: string
  situation: string
  steps: string[]
  action_taken: string
  outcome: string
  reward: number
  created_at: string
}

interface Props {
  decisions: DecisionEvent[]
}

const TIER_COLOR: Record<string, string> = {
  GREEN: '#30FF6A',
  YELLOW: '#FFB800',
  RED: '#FF3B30',
}

function scoreToTier(score: number): 'GREEN' | 'YELLOW' | 'RED' {
  if (score >= 0.7) return 'GREEN'
  if (score >= 0.4) return 'YELLOW'
  return 'RED'
}

function formatTs(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function ReasoningChainView({ chain }: { chain: ReasoningChain | null }) {
  if (!chain) return null
  return (
    <div style={{
      marginTop: 6,
      padding: '8px 10px',
      background: 'rgba(0,212,255,0.06)',
      border: '1px solid rgba(0,212,255,0.2)',
      borderRadius: 2,
      fontSize: '0.6rem',
      color: 'var(--jarvis-text)',
      lineHeight: 1.6,
    }}>
      <div style={{ color: 'var(--jarvis-text-dim)', marginBottom: 4 }}>REASONING CHAIN</div>
      <div style={{ marginBottom: 4 }}>
        <span style={{ color: 'var(--jarvis-text-dim)' }}>SITUATION: </span>
        {chain.situation || '—'}
      </div>
      <div style={{ marginBottom: 4 }}>
        <span style={{ color: 'var(--jarvis-text-dim)' }}>STEPS: </span>
        {chain.steps.length > 0
          ? chain.steps.join(' → ')
          : '—'}
      </div>
      <div style={{ marginBottom: 4 }}>
        <span style={{ color: 'var(--jarvis-text-dim)' }}>OUTCOME: </span>
        {chain.outcome || '—'}
      </div>
      <div>
        <span style={{ color: 'var(--jarvis-text-dim)' }}>REWARD: </span>
        <span style={{ color: chain.reward >= 0.7 ? '#30FF6A' : '#FFB800' }}>
          {chain.reward.toFixed(2)}
        </span>
      </div>
    </div>
  )
}

export function DecisionTrace({ decisions }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [chains, setChains] = useState<Record<string, ReasoningChain | null>>({})
  const [loading, setLoading] = useState<string | null>(null)

  const handleClick = async (decision: DecisionEvent) => {
    const key = decision.id
    if (expandedId === key) {
      setExpandedId(null)
      return
    }
    setExpandedId(key)
    if (chains[key] !== undefined) return

    setLoading(key)
    try {
      const res = await fetch(
        `/brain/reasoning/chains?situation=${encodeURIComponent(decision.action_type)}&limit=1`
      )
      if (res.ok) {
        const body = await res.json()
        const chain = body.chains?.[0] ?? null
        setChains(prev => ({ ...prev, [key]: chain }))
      } else {
        setChains(prev => ({ ...prev, [key]: null }))
      }
    } catch {
      setChains(prev => ({ ...prev, [key]: null }))
    } finally {
      setLoading(null)
    }
  }

  if (decisions.length === 0) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: 80, color: 'var(--jarvis-text-dim)', fontSize: '0.65rem',
      }}>
        Awaiting VECTOR decisions...
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, overflowY: 'auto', maxHeight: '100%' }}>
      <div className="label" style={{ marginBottom: 4 }}>
        DECISION TRACE — LAST {decisions.length}
      </div>
      {decisions.map((d, idx) => {
        const tier = d.tier ?? scoreToTier(d.score)
        const color = TIER_COLOR[tier]
        const isExpanded = expandedId === d.id
        const chain = chains[d.id]
        return (
          <div
            key={d.id}
            onClick={() => handleClick(d)}
            style={{
              padding: '6px 8px',
              border: '1px solid',
              borderColor: isExpanded ? color : 'var(--jarvis-border)',
              borderRadius: 2,
              background: isExpanded ? `rgba(0,0,0,0.2)` : 'transparent',
              cursor: 'pointer',
              position: 'relative',
              transition: 'border-color 0.2s',
            }}
          >
            {/* Timeline connector */}
            {idx < decisions.length - 1 && (
              <div style={{
                position: 'absolute', left: 13, bottom: -5, width: 1, height: 5,
                background: 'var(--jarvis-border)',
              }} />
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {/* Tier dot */}
              <div style={{
                width: 6, height: 6, borderRadius: '50%',
                background: color, boxShadow: `0 0 6px ${color}`, flexShrink: 0,
              }} />
              <span style={{
                fontSize: '0.65rem', color: 'var(--jarvis-text)',
                flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {d.action_type}
              </span>
              <span style={{ fontSize: '0.55rem', color: color, flexShrink: 0 }}>
                {(d.score * 100).toFixed(0)}%
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3, paddingLeft: 12 }}>
              <span style={{ fontSize: '0.55rem', color: 'var(--jarvis-text-dim)' }}>
                {tier}
              </span>
              <span style={{ fontSize: '0.55rem', color: 'var(--jarvis-text-muted)' }}>
                {formatTs(d.ts)}
              </span>
            </div>

            {isExpanded && (
              loading === d.id
                ? <div style={{ marginTop: 6, fontSize: '0.6rem', color: 'var(--jarvis-text-dim)' }}>
                    Loading reasoning chain...
                  </div>
                : <ReasoningChainView chain={chain ?? null} />
            )}
          </div>
        )
      })}
    </div>
  )
}
