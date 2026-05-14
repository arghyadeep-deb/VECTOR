import { useState } from 'react'
import { Z } from '../lib/zIndex'

type VCStatus = 'idle' | 'launching' | 'running' | 'error'

export default function VectorCodePanel() {
  const [status, setStatus] = useState<VCStatus>('idle')
  const [msg, setMsg] = useState('')

  const launch = async () => {
    if (status === 'launching') return
    setStatus('launching')
    setMsg('Opening terminal…')
    try {
      const r = await fetch('/vectorcode/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'run' }),
      })
      const d = await r.json()
      if (d.status === 'ok') {
        setStatus('running')
        setMsg('VectorCode active')
        setTimeout(() => { setStatus('idle'); setMsg('') }, 6000)
      } else {
        setStatus('error')
        setMsg(d.detail || 'Launch failed')
        setTimeout(() => { setStatus('idle'); setMsg('') }, 4000)
      }
    } catch (e) {
      setStatus('error')
      setMsg('Server unreachable')
      setTimeout(() => { setStatus('idle'); setMsg('') }, 4000)
    }
  }

  const borderColor =
    status === 'running' ? 'rgba(0,255,136,0.35)' :
    status === 'error'   ? 'rgba(255,61,61,0.35)' :
    status === 'launching' ? 'rgba(255,179,0,0.25)' :
    'rgba(0,212,255,0.08)'

  const glowColor =
    status === 'running' ? '0 0 18px rgba(0,255,136,0.18)' :
    status === 'error'   ? '0 0 18px rgba(255,61,61,0.18)' :
    '0 0 14px rgba(0,212,255,0.04)'

  const labelColor =
    status === 'running' ? '#00FF88' :
    status === 'error'   ? '#FF3D3D' :
    status === 'launching' ? '#FFB300' :
    '#00CFFF'

  return (
    <div
      onClick={launch}
      style={{
        width: '100%',
        zIndex: Z.METRICS,
        background: 'rgba(5,13,26,0.88)',
        backdropFilter: 'blur(14px)',
        WebkitBackdropFilter: 'blur(14px)',
        border: `1px solid ${borderColor}`,
        boxShadow: glowColor,
        cursor: status === 'launching' ? 'wait' : 'pointer',
        transition: 'border-color 0.3s ease, box-shadow 0.3s ease',
        userSelect: 'none',
      }}
    >
      {/* Header row */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '6px 10px',
        borderBottom: '1px solid rgba(0,207,255,0.06)',
      }}>
        <span style={{
          fontFamily: "'Orbitron', sans-serif", fontSize: 11,
          color: labelColor, letterSpacing: '0.15em',
          transition: 'color 0.3s ease',
        }}>
          VECTORCODE
        </span>
        {/* Status dot */}
        <span style={{
          width: 6, height: 6, borderRadius: '50%',
          background: labelColor,
          boxShadow: `0 0 8px ${labelColor}`,
          display: 'inline-block',
          animation: status === 'launching' ? 'v-pulse 0.8s ease-in-out infinite' :
                     status === 'running'   ? 'v-pulse 2s ease-in-out infinite' : 'none',
        }} />
      </div>

      {/* Body */}
      <div style={{ padding: '6px 10px 8px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
          color: '#1a6688', letterSpacing: '0.05em',
        }}>
          {status === 'idle'      && 'Click to activate in terminal'}
          {status === 'launching' && '⟳ ' + msg}
          {status === 'running'   && '✓ ' + msg}
          {status === 'error'     && '✗ ' + msg}
        </div>

        {/* Mode tag */}
        <div style={{ display: 'flex', gap: 4, marginTop: 2 }}>
          {['run', 'auto', 'hybrid'].map((m) => (
            <span key={m} style={{
              fontFamily: "'Orbitron', sans-serif", fontSize: 8,
              color: m === 'run' ? '#00CFFF' : '#1a4466',
              border: `1px solid ${m === 'run' ? 'rgba(0,207,255,0.25)' : 'rgba(0,207,255,0.06)'}`,
              padding: '1px 5px', letterSpacing: '0.1em',
            }}>
              {m.toUpperCase()}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
