import { useState, useEffect, useCallback } from 'react'
import { Z } from '../lib/zIndex'

type VCStatus = 'idle' | 'launching' | 'running' | 'error'
type VCMode = 'run' | 'auto' | 'hybrid'

const MODE_COLORS: Record<VCMode, string> = {
  run: '#4FC3F7',
  auto: '#4FC3F7',
  hybrid: '#64B5F6',
}

const MODE_DOT_COLORS: Record<VCMode | 'idle', string> = {
  run: '#4FC3F7',
  auto: '#4FC3F7',
  hybrid: '#42A5F5',
  idle: '#444444',
}

let _csrfToken = ''

async function fetchCsrfToken(): Promise<string> {
  try {
    const r = await fetch('/csrf-token', { cache: 'no-store' })
    const d = await r.json()
    _csrfToken = d.csrf_token ?? ''
  } catch { /* ignore */ }
  return _csrfToken
}

export default function VectorCodePanel() {
  const [status, setStatus] = useState<VCStatus>('idle')
  const [msg, setMsg] = useState('')
  const [activeMode, setActiveMode] = useState<VCMode>('run')
  const [actionLog, setActionLog] = useState<{ time: string; action: string }[]>([])
  const [modeDotColor, setModeDotColor] = useState<string>('#444444')

  useEffect(() => { fetchCsrfToken() }, [])

  const logAction = useCallback((action: string) => {
    const now = new Date()
    const ts = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
    setActionLog(prev => [...prev.slice(-1), { time: ts, action }])
  }, [])

  const launch = async (mode?: VCMode) => {
    const m = mode || activeMode
    if (status === 'launching') return
    if (!_csrfToken) await fetchCsrfToken()
    setStatus('launching')
    setMsg(`Starting ${m}...`)
    try {
      const r = await fetch('/vectorcode/launch', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': _csrfToken,
        },
        body: JSON.stringify({ mode: m }),
      })
      const d = await r.json()
      if (d.status === 'ok') {
        setStatus('running')
        setMsg(`${m} active`)
        setModeDotColor(MODE_DOT_COLORS[m])
        logAction(`${m.toUpperCase()} mode activated`)
        setTimeout(() => { setStatus('idle'); setMsg(''); setModeDotColor('#444444') }, 6000)
      } else {
        setStatus('error')
        setMsg(d.detail || 'Launch failed')
        logAction(`ERROR: ${d.detail || 'Launch failed'}`)
        setTimeout(() => { setStatus('idle'); setMsg('') }, 4000)
      }
    } catch (e) {
      setStatus('error')
      setMsg('Server unreachable')
      logAction('ERROR: Server unreachable')
      setTimeout(() => { setStatus('idle'); setMsg('') }, 4000)
    }
  }

  const setMode = (m: VCMode) => {
    setActiveMode(m)
    if (status === 'idle') {
      setModeDotColor(MODE_DOT_COLORS[m])
    }
    launch(m)
  }

  const dotAnim = status === 'launching' ? 'v-pulse 0.8s ease-in-out infinite'
    : status === 'running' ? 'v-pulse 2s ease-in-out infinite'
    : activeMode !== 'run' && status === 'idle' ? 'v-pulse 2.5s ease-in-out infinite'
    : 'none'

  const borderColor =
    status === 'running' ? 'rgba(79,195,247,0.35)' :
    status === 'error'   ? 'rgba(239,83,80,0.35)' :
    status === 'launching' ? 'rgba(66,165,245,0.25)' :
    'rgba(79,195,247,0.08)'

  const glowColor =
    status === 'running' ? '0 0 18px rgba(79,195,247,0.18)' :
    status === 'error'   ? '0 0 18px rgba(239,83,80,0.18)' :
    '0 0 14px rgba(79,195,247,0.04)'

  const labelColor =
    status === 'running' ? '#4FC3F7' :
    status === 'error'   ? '#FF3D3D' :
    status === 'launching' ? '#42A5F5' :
    '#4FC3F7'

  const currentDotColor = status === 'running' || status === 'launching' ? labelColor
    : activeMode !== 'run' ? MODE_DOT_COLORS[activeMode]
    : '#4FC3F7'

  return (
    <div
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
        borderBottom: '1px solid rgba(79,195,247,0.06)',
      }}>
        <span style={{
          fontFamily: "'Orbitron', sans-serif", fontSize: 11,
          color: labelColor, letterSpacing: '0.15em',
          transition: 'color 0.3s ease',
        }}>
          VECTORCODE
        </span>
        {/* Status dots: main dot + mode dot */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{
            width: 5, height: 5, borderRadius: '50%',
            background: modeDotColor,
            boxShadow: `0 0 6px ${modeDotColor}`,
            display: 'inline-block',
            animation: dotAnim,
          }} />
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: currentDotColor,
            boxShadow: `0 0 8px ${currentDotColor}`,
            display: 'inline-block',
            animation: status === 'launching' ? 'v-pulse 0.8s ease-in-out infinite' :
                       status === 'running'   ? 'v-pulse 2s ease-in-out infinite' : 'none',
          }} />
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: '6px 10px 8px', display: 'flex', flexDirection: 'column', gap: 3 }} onClick={() => status === 'idle' && launch()}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
          color: '#66ccee', letterSpacing: '0.05em',
        }}>
          {status === 'idle'      && 'Click to activate'}
          {status === 'launching' && '⟳ ' + msg}
          {status === 'running'   && '✓ ' + msg}
          {status === 'error'     && '✗ ' + msg}
        </div>

        {/* Mode tags */}
        <div style={{ display: 'flex', gap: 4, marginTop: 1 }}>
          {(['run', 'auto', 'hybrid'] as VCMode[]).map((m) => (
            <span key={m} onClick={(e) => { e.stopPropagation(); setMode(m) }}
              style={{
                fontFamily: "'Orbitron', sans-serif", fontSize: 8,
                color: activeMode === m ? '#4FC3F7' : '#4499bb',
                border: `1px solid ${activeMode === m ? 'rgba(79,195,247,0.35)' : 'rgba(79,195,247,0.12)'}`,
                padding: '1px 5px', letterSpacing: '0.1em',
                cursor: 'pointer',
                background: activeMode === m ? 'rgba(79,195,247,0.06)' : 'transparent',
                transition: 'all 0.2s',
              }}>
              {m.toUpperCase()}
            </span>
          ))}
        </div>

        {/* Active mode status line */}
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 8,
          color: '#81D4FA', letterSpacing: '0.08em', marginTop: 2,
          paddingTop: 3, borderTop: '1px solid rgba(79,195,247,0.06)',
        }}>
          {status === 'running' ? `${activeMode.toUpperCase()} › active` :
           status === 'idle' && activeMode !== 'run' ? `${activeMode.toUpperCase()} › standby` :
           'RUN › idle'}
        </div>

        {/* Mini action log */}
        {actionLog.length > 0 && (
          <div style={{ marginTop: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
            {actionLog.slice(-2).map((entry, i) => (
              <div key={i} style={{
                display: 'flex', gap: 4,
                fontFamily: "'JetBrains Mono', monospace", fontSize: 7,
                color: entry.action.includes('ERROR') ? '#EF5350' : '#64B5F6',
              }}>
                <span style={{ color: '#1a4466', flexShrink: 0 }}>{entry.time}</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.action}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
