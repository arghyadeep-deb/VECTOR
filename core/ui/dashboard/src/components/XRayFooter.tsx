/* ═══════════════════════════════════════════════════════════════════════════
   VECTOR — XRayFooter + ToolCallCard
   Show tool calls, token costs, energy consumption transparently
   under each assistant message. Borrowed pattern from VectorCode but
   restyled for VECTOR HUD.
   ═══════════════════════════════════════════════════════════════════════════ */
import { useState } from 'react'

export interface ToolCall {
  id: string
  name: string
  args: Record<string, any>
  result?: any
  duration_ms?: number
  error?: string
  /** ISO timestamp */
  ts?: string
}

export interface XRayMetrics {
  model?: string
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  latency_ms?: number
  energy_joules?: number
  power_watts?: number
  cost_usd?: number
}

/* ── ToolCallCard ───────────────────────────────────────────────────────── */

export function ToolCallCard({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false)
  const failed = !!call.error

  return (
    <div style={{
      marginTop: 6,
      borderLeft: `2px solid ${failed ? 'var(--red)' : 'var(--cyan-dim)'}`,
      background: failed ? 'rgba(255,51,51,0.04)' : 'rgba(0,212,255,0.03)',
      borderRadius: 2,
    }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%',
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '6px 10px',
          background: 'transparent', border: 'none',
          color: 'inherit', cursor: 'pointer',
          fontFamily: 'inherit', textAlign: 'left',
        }}
      >
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: 1.2,
          color: failed ? 'var(--red)' : 'var(--cyan)',
          fontFamily: "'Orbitron', sans-serif",
          width: 64, flexShrink: 0,
        }}>
          {failed ? 'TOOL: ✗' : 'TOOL: ✓'}
        </span>
        <code style={{
          fontSize: 11, color: '#e6f1ff',
          fontFamily: "'JetBrains Mono', monospace",
          flex: 1,
        }}>
          {call.name}
          <span style={{ color: 'var(--cyan-dim)' }}>
            ({Object.keys(call.args || {}).length} args)
          </span>
        </code>
        {call.duration_ms !== undefined && (
          <span style={{ fontSize: 10, color: 'var(--cyan-dim)' }}>
            {call.duration_ms}ms
          </span>
        )}
        <span style={{ fontSize: 10, color: 'var(--cyan-dim)' }}>{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div style={{
          padding: '6px 10px 10px 76px',
          fontSize: 10, fontFamily: "'JetBrains Mono', monospace",
          color: 'var(--cyan-dim)',
        }}>
          <div style={{ marginBottom: 4 }}>
            <span style={{ color: 'var(--cyan)' }}>args</span>{' '}
            <code style={{ color: '#e6f1ff' }}>
              {JSON.stringify(call.args, null, 2).split('\n').slice(0, 8).join('\n')}
            </code>
          </div>
          {call.error ? (
            <div>
              <span style={{ color: 'var(--red)' }}>error</span>{' '}
              <code style={{ color: '#ffcccc' }}>{call.error}</code>
            </div>
          ) : call.result !== undefined && (
            <div>
              <span style={{ color: 'var(--green)' }}>result</span>{' '}
              <code style={{ color: '#e6f1ff' }}>
                {typeof call.result === 'string'
                  ? call.result.slice(0, 240)
                  : JSON.stringify(call.result, null, 2).slice(0, 240)}
              </code>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ── XRayFooter ─────────────────────────────────────────────────────────── */

export function XRayFooter({ metrics, calls }: { metrics?: XRayMetrics; calls?: ToolCall[] }) {
  if (!metrics && (!calls || calls.length === 0)) return null

  const totalT = metrics?.total_tokens ?? ((metrics?.prompt_tokens || 0) + (metrics?.completion_tokens || 0))
  const e = metrics?.energy_joules ?? 0
  const lat = metrics?.latency_ms

  return (
    <div style={{
      marginTop: 8,
      padding: '6px 0',
      borderTop: '1px dashed var(--panel-border)',
      fontSize: 10,
      fontFamily: "'JetBrains Mono', monospace",
      color: 'var(--cyan-dim)',
    }}>
      {/* Tool calls */}
      {calls && calls.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          {calls.map((c) => <ToolCallCard key={c.id} call={c} />)}
        </div>
      )}

      {/* Metrics line */}
      {metrics && (
        <div style={{
          display: 'flex', flexWrap: 'wrap',
          gap: 14, alignItems: 'center',
        }}>
          {metrics.model && (
            <span>
              <em style={{ color: 'var(--cyan)' }}>model</em>{' '}
              <code style={{ color: '#e6f1ff' }}>{metrics.model}</code>
            </span>
          )}
          {totalT > 0 && (
            <span>
              <em style={{ color: 'var(--cyan)' }}>tok</em>{' '}
              <code style={{ color: '#e6f1ff' }}>
                {metrics.prompt_tokens ?? '?'}→{metrics.completion_tokens ?? '?'}
                <span style={{ color: 'var(--cyan-dim)' }}> ({totalT})</span>
              </code>
            </span>
          )}
          {lat !== undefined && (
            <span>
              <em style={{ color: 'var(--cyan)' }}>lat</em>{' '}
              <code style={{ color: '#e6f1ff' }}>{lat}ms</code>
            </span>
          )}
          {e > 0 && (
            <span>
              <em style={{ color: 'var(--cyan)' }}>energy</em>{' '}
              <code style={{ color: '#e6f1ff' }}>
                {e >= 1 ? `${e.toFixed(2)}J` : `${(e * 1000).toFixed(1)}mJ`}
              </code>
            </span>
          )}
          {metrics.power_watts !== undefined && metrics.power_watts > 0 && (
            <span>
              <em style={{ color: 'var(--cyan)' }}>power</em>{' '}
              <code style={{ color: '#e6f1ff' }}>{metrics.power_watts.toFixed(1)}W</code>
            </span>
          )}
          {metrics.cost_usd !== undefined && metrics.cost_usd > 0 && (
            <span>
              <em style={{ color: 'var(--amber)' }}>$</em>{' '}
              <code style={{ color: '#ffd485' }}>${metrics.cost_usd.toFixed(4)}</code>
            </span>
          )}
        </div>
      )}
    </div>
  )
}
