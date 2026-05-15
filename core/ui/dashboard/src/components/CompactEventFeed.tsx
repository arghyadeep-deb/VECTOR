import { useEffect, useRef, useState, useMemo } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { api, formatTs } from '../lib/api'
import { usePoll } from '../lib/poller'

const badgeStyles: Record<string, { bg: string; color: string; label: string }> = {
  CHAT: { bg: '#003d6b', color: '#4FC3F7', label: 'CHAT' },
  DEC: { bg: '#003300', color: '#4FC3F7', label: 'DEC' },
  OBS: { bg: '#1a1a1a', color: '#666666', label: 'OBS' },
  GOVE: { bg: '#1a0040', color: '#64B5F6', label: 'GOVE' },
}

function getBadge(type: string) {
  const t = type.toLowerCase()
  if (t.includes('chat')) return badgeStyles.CHAT
  if (t.includes('decision')) {
    const isRejected = t.includes('reject') || t.includes('veto') || t.includes('denied')
    return isRejected
      ? { bg: '#222222', color: '#555555', label: 'DEC' }
      : badgeStyles.DEC
  }
  if (t.includes('observe') || t.includes('observation') || t.includes('memory') || t.includes('learn')) return badgeStyles.OBS
  if (t.includes('gov') || t.includes('council') || t.includes('goal')) return badgeStyles.GOVE
  if (t.includes('error') || t.includes('warn')) return { bg: '#3d0000', color: '#FF3D3D', label: 'ERR' }
  if (t.includes('action') || t.includes('exec')) return { bg: '#002a3d', color: '#4FC3F7', label: 'ACT' }
  return badgeStyles.OBS
}

function getLS(key: string, def: string): string {
  try { return localStorage.getItem(key) ?? def } catch { return def }
}
function setLS(key: string, val: string) {
  try { localStorage.setItem(key, val) } catch {}
}

export default function CompactEventFeed() {
  const storeEvents = useVectorStore((s) => s.events)
  const setEvents = useVectorStore((s) => s.setEvents)
  const scrollRef = useRef<HTMLDivElement>(null!)
  const [paused, setPaused] = useState(false)
  const [ticker, setTicker] = useState(() => getLS('v-compact-ticker', '0') === '1')
  const [loading, setLoading] = useState(true)

  usePoll({
    key: 'events',
    fetcher: () => api.memoryRecent(30),
    intervalMs: 5000,
    onSuccess: (d) => {
      setEvents(d.events || [])
      setLoading(false)
    },
    onError: () => setLoading(false),
  })

  const displayEvents = useMemo(() => storeEvents.slice(0, 50), [storeEvents])

  useEffect(() => {
    if (!paused && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [displayEvents, paused])

  const toggleTicker = () => {
    setTicker((p) => { const n = !p; setLS('v-compact-ticker', n ? '1' : '0'); return n })
  }

  // Ticker mode
  if (ticker) {
    const marqueeText = displayEvents.length > 0
      ? displayEvents.slice(0, 50).map((ev) =>
        `[${formatTs(ev.timestamp)}] ${getBadge(ev.event_type).label} › ${ev.content?.slice(0, 60) || ''}`
      ).join('  ›  ')
      : 'AWAITING TELEMETRY...'
    return (
      <div style={{ position: 'fixed', top: 52, left: 237, width: 380, height: 220, zIndex: 50, background: 'rgba(4,12,24,0.92)', border: '1px solid rgba(79,195,247,0.08)', boxShadow: '0 0 30px rgba(79,195,247,0.03)' }}>
        <div style={{ height: 14, display: 'flex', alignItems: 'center', padding: '0 6px' }}>
          <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#1a6b8a', flex: 1 }}>
            <span style={{ animation: 'compactMarquee 40s linear infinite', display: 'inline-block', whiteSpace: 'nowrap' }}>{marqueeText}</span>
          </div>
          <button onClick={toggleTicker} style={{ background: 'transparent', border: 'none', color: '#1a6b8a', cursor: 'pointer', fontFamily: "'JetBrains Mono', monospace", fontSize: 9, flexShrink: 0, padding: 0, lineHeight: 1 }}>-</button>
        </div>
        <style>{`@keyframes compactMarquee{0%{transform:translateX(100%)}100%{transform:translateX(-100%)}}`}</style>
      </div>
    )
  }

  return (
    <div style={{ position: 'fixed', top: 52, left: 237, width: 380, height: 220, zIndex: 50, background: 'rgba(4,12,24,0.92)', border: '1px solid rgba(79,195,247,0.08)', boxShadow: '0 0 30px rgba(79,195,247,0.03)' }}>
      <div style={{ height: 18, display: 'flex', alignItems: 'center', padding: '0 6px', borderBottom: '1px solid rgba(0,207,255,0.06)' }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 9, color: '#4FC3F7', letterSpacing: '0.15em', fontWeight: 500 }}>EVENT FEED</span>
        <button onClick={toggleTicker} style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid rgba(0,207,255,0.12)', color: '#1a6688', cursor: 'pointer', padding: '0 4px', fontFamily: "'Orbitron', sans-serif", fontSize: 7, lineHeight: '14px', borderRadius: 2, transition: 'all 0.15s' }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#4FC3F7'; e.currentTarget.style.borderColor = 'rgba(0,212,255,0.3)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#1a6688'; e.currentTarget.style.borderColor = 'rgba(0,212,255,0.12)' }}
        >=</button>
      </div>
      <div
        ref={scrollRef}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        style={{ height: 200, overflowY: 'auto', overflowX: 'hidden', scrollbarWidth: 'thin', scrollbarColor: '#4FC3F722 transparent' }}
      >
        {loading ? (
          <div style={{ height: 18, display: 'flex', alignItems: 'center', padding: '0 6px', fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#1a4466', letterSpacing: '0.1em' }}>CONNECTING...</div>
        ) : displayEvents.length === 0 ? (
          <div style={{ height: 18, display: 'flex', alignItems: 'center', padding: '0 6px', fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#1a4466', letterSpacing: '0.1em' }}>AWAITING TELEMETRY...</div>
        ) : (
          displayEvents.map((ev, i) => {
            const badge = getBadge(ev.event_type)
            const isError = badge.label === 'ERR'
            return (
              <div key={ev.id || `e-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 4, height: 18, padding: '0 6px', borderBottom: '1px solid #0a2540', fontSize: 9, borderLeft: isError ? '3px solid #FF3D3D' : 'none', paddingLeft: isError ? 3 : 6 }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: '#1a6b8a', width: 42, flexShrink: 0 }}>{formatTs(ev.timestamp)}</span>
                <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, padding: '1px 4px', background: badge.bg, color: badge.color, flexShrink: 0, letterSpacing: '0.05em' }}>{badge.label}</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: isError ? '#FF3D3D' : '#7ecfed', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{ev.content?.slice(0, 80) || ''}</span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
