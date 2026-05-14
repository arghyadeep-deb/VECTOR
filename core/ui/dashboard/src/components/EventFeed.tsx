import { useEffect, useRef, useState, useMemo } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { api, formatTs, type MemoryEvent } from '../lib/api'
import Sparkline from './Sparkline'
import { panelStyle, panelHeader } from '../lib/panelStyles'
import { usePoll } from '../lib/poller'
import { Z } from '../lib/zIndex'

const headerId: React.CSSProperties = {
  color: '#004466', fontSize: 8, fontFamily: "'JetBrains Mono', monospace",
}

const scrollArea: React.CSSProperties = {
  flex: 1, overflowY: 'auto', padding: '6px 0',
}

const eventRow: React.CSSProperties = {
  display: 'flex', gap: 8, padding: '4px 12px',
  borderBottom: '1px solid rgba(0,207,255,0.03)',
  alignItems: 'center', position: 'relative' as const,
}

const colorBar = (color: string): React.CSSProperties => ({
  position: 'absolute' as const, left: 0, top: 2, bottom: 2, width: 3,
  background: color, borderRadius: '0 2px 2px 0', boxShadow: `0 0 6px ${color}`,
})

const eventTime: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#1a4466',
  whiteSpace: 'nowrap', minWidth: 56, flexShrink: 0,
}

const eventBadge: React.CSSProperties = {
  fontFamily: "'Orbitron', sans-serif", fontSize: 8, fontWeight: 500,
  padding: '1px 5px', whiteSpace: 'nowrap', flexShrink: 0, letterSpacing: '0.1em',
}

const eventContent: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#66aacc',
  lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
}

const empty: React.CSSProperties = {
  fontFamily: "'Orbitron', sans-serif", fontSize: 10, fontWeight: 300,
  color: '#1a4466', textAlign: 'center', padding: '30px 0', letterSpacing: '0.15em',
}

function badgeColor(type: string): string {
  const t = type.toLowerCase()
  if (t.includes('chat') || t.includes('message')) return '#00CFFF'
  if (t.includes('error') || t.includes('fail') || t.includes('warn')) return '#ff3355'
  if (t.includes('goal') || t.includes('council') || t.includes('gov')) return '#ffaa00'
  if (t.includes('action') || t.includes('exec') || t.includes('decision')) return '#00ff88'
  if (t.includes('memory') || t.includes('learn') || t.includes('observe')) return '#aa66ff'
  if (t.includes('system') || t.includes('context') || t.includes('permission')) return '#3388aa'
  return '#3388aa'
}

function badgeLabel(type: string): string {
  const t = type.toLowerCase()
  if (t.includes('chat')) return 'CHAT'
  if (t.includes('decision')) return 'DEC'
  if (t.includes('action') || t.includes('exec')) return 'ACT'
  if (t.includes('council') || t.includes('gov')) return 'GOVE'
  if (t.includes('reflection')) return 'RFLCT'
  if (t.includes('goal')) return 'GOAL'
  if (t.includes('observation') || t.includes('observe')) return 'OBS'
  if (t.includes('memory') || t.includes('learn')) return 'MEM'
  if (t.includes('error') || t.includes('warn')) return 'ERR'
  if (t.includes('system')) return 'SYS'
  if (t.includes('context')) return 'CTX'
  if (t.includes('permission') || t.includes('gateway')) return 'GATE'
  return type.slice(0, 4).toUpperCase()
}

function getLS(key: string, def: string): string {
  try { return localStorage.getItem(key) ?? def } catch { return def }
}
function setLS(key: string, val: string) {
  try { localStorage.setItem(key, val) } catch {}
}

export default function EventFeed() {
  const storeEvents = useVectorStore((s) => s.events)
  const setEvents = useVectorStore((s) => s.setEvents)
  const openPanel = useVectorStore((s) => s.openPanel)
  const scrollRef = useRef<HTMLDivElement>(null!)
  const [loading, setLoading] = useState(true)
  const [connectionError, setConnectionError] = useState(false)
  const [collapsed, setCollapsed] = useState(() => getLS('v-feed-collapsed', '0') === '1')
  const [ticker, setTicker] = useState(() => getLS('v-feed-ticker', '0') === '1')

  usePoll({
    key: 'events',
    fetcher: () => api.memoryRecent(30),
    intervalMs: 5000,
    onSuccess: (d) => {
      setEvents(d.events || [])
      setLoading(false)
      setConnectionError(false)
    },
    onError: (err) => {
      setLoading(false)
      setConnectionError(true)
    },
  })

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0
  }, [storeEvents])

  const displayEvents = useMemo(() => {
    return storeEvents.slice(0, 28)
  }, [storeEvents])

  const toggleCollapse = () => {
    setCollapsed((p) => { const n = !p; setLS('v-feed-collapsed', n ? '1' : '0'); return n })
  }

  const toggleTicker = () => {
    setTicker((p) => { const n = !p; setLS('v-feed-ticker', n ? '1' : '0'); return n })
  }

  if (ticker) {
    const marqueeText = displayEvents.length > 0
      ? displayEvents.slice(0, 40).map((ev) =>
        `[${formatTs(ev.timestamp)}] ${badgeLabel(ev.event_type)} › ${ev.content?.slice(0, 50) || ''}`
      ).join(' › ')
      : 'AWAITING TELEMETRY...'
    return (
      <div style={{ position: 'fixed', top: 42, left: 0, right: 0, height: 20,   zIndex: Z.TICKER, background: 'rgba(2, 18, 32, 0.95)', borderBottom: '1px solid rgba(0,207,255,0.1)', overflow: 'hidden', display: 'flex', alignItems: 'center' }}>
        <div style={{ whiteSpace: 'nowrap' as const, animation: 'marquee 60s linear infinite', fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: '#3388aa', paddingLeft: 20 }}>
          {marqueeText}
        </div>
        <style>{`@keyframes marquee{0%{transform:translateX(100%)}100%{transform:translateX(-100%)}}`}</style>
          <button onClick={toggleTicker} style={{ position: 'absolute', right: 4, top: 1, background: 'transparent', border: '1px solid rgba(0,212,255,0.12)', color: '#1a6688', cursor: 'pointer', padding: '1px 5px', fontFamily: "'Orbitron', sans-serif", fontSize: 7, zIndex: Z.TICKER, borderRadius: 3 }}>TICKER</button>
      </div>
    )
  }

  const headerExtras: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 4, marginLeft: 'auto',
  }
  const iconBtn: React.CSSProperties = {
    background: 'transparent', border: '1px solid rgba(0,212,255,0.12)', color: '#1a6688', cursor: 'pointer', padding: '1px 5px', fontFamily: "'Orbitron', sans-serif", fontSize: 7, lineHeight: 1, transition: 'all 0.15s', borderRadius: 3,
  }

  return (
    <div className="corner-bracket" style={{ ...panelStyle(), display: 'flex', flexDirection: 'column', minHeight: 0, flex: '0 0 auto', height: collapsed ? 30 : 340, background: 'rgba(5,13,26,0.88)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', border: '1px solid rgba(0,212,255,0.1)' }}>
      {connectionError && (
        <div style={{ background: '#ff880033', borderBottom: '1px solid #ff880066', padding: '3px 12px', fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#ffaa00', textAlign: 'center', letterSpacing: '0.1em' }}>
          CONNECTION LOST — RETRYING...
        </div>
      )}
      <div style={{ ...panelHeader(), height: 30, minHeight: 30 }}>
        <span style={{ color: '#00d4ff' }}>Event Feed</span>
        <span style={headerId}>FEED</span>
        <div style={headerExtras}>
          <button style={iconBtn} onClick={toggleTicker}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#00d4ff'; e.currentTarget.style.borderColor = 'rgba(0,212,255,0.3)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#1a6688'; e.currentTarget.style.borderColor = 'rgba(0,212,255,0.12)' }}
          >TICKER <span style={{ display: 'inline-block', width: 3, height: 3, borderRadius: '50%', background: ticker ? '#00d4ff' : '#1a6688', verticalAlign: 'middle', marginLeft: 2 }} /></button>
          <button style={iconBtn} onClick={toggleCollapse}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#00d4ff'; e.currentTarget.style.borderColor = 'rgba(0,212,255,0.3)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#1a6688'; e.currentTarget.style.borderColor = 'rgba(0,212,255,0.12)' }}
          >{collapsed ? '▼' : '▲'}</button>
        </div>
      </div>
      {!collapsed && (
        <div ref={scrollRef} style={scrollArea}>
          {loading ? (
            <div style={empty}>CONNECTING...</div>
          ) : displayEvents.length === 0 ? (
            <div style={empty}>AWAITING TELEMETRY...</div>
          ) : (
            displayEvents.map((ev, i) => {
              const bc = badgeColor(ev.event_type)
              const isDec = badgeLabel(ev.event_type) === 'DEC'
              return (
                <div
                  key={ev.id || `e-${i}`}
                  style={{ ...eventRow, paddingLeft: 18, cursor: isDec ? 'pointer' : 'default', animation: 'fade-in-up 0.3s ease-out' }}
                  onClick={isDec ? () => openPanel({ id: 'decision', type: 'decision' }) : undefined}
                  onMouseEnter={isDec ? (e) => { e.currentTarget.style.background = 'rgba(0,212,255,0.03)' } : undefined}
                  onMouseLeave={isDec ? (e) => { e.currentTarget.style.background = 'transparent' } : undefined}
                >
                  <div style={colorBar(bc)} />
                  <span style={eventTime}>{formatTs(ev.timestamp)}</span>
                  <span style={{ ...eventBadge, color: bc, border: `1px solid ${bc}33` }}>{badgeLabel(ev.event_type)}</span>
                  <span style={eventContent}>{ev.content?.slice(0, 100) || ''}</span>
                  <Sparkline color={bc} />
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
