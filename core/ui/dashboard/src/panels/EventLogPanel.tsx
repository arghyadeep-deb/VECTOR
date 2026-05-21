import { useEffect, useRef } from 'react'
import { useVectorStore } from '../store/vectorStore'

export default function EventLogPanel() {
  const events = useVectorStore((s) => s.events)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = 0
    }
  }, [events.length])

  const importanceColor = (imp?: string) => {
    switch (imp) {
      case 'high': return '#FF4444'
      case 'critical': return '#FF0044'
      default: return '#557799'
    }
  }

  const eventTypeColor = (type: string) => {
    const t = type.toLowerCase()
    if (t.includes('error') || t.includes('critical')) return '#FF4444'
    if (t.includes('think')) return '#FFAA00'
    if (t.includes('act') || t.includes('exec')) return '#44FF88'
    if (t.includes('chat')) return '#00CFFF'
    if (t.includes('govern')) return '#4488FF'
    return '#6688aa'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ fontSize: 9, color: '#1a6688', padding: '8px 8px 4px', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
        Event Log · {events.length} recent
      </div>
      <div ref={listRef} style={{
        flex: 1, overflow: 'auto', padding: '0 8px 8px',
      }}>
        {events.length === 0 ? (
          <div style={{ fontSize: 10, color: '#335566', padding: 12, textAlign: 'center' }}>
            No events
          </div>
        ) : (
          events.slice(0, 40).map((e) => {
            const ts = e.timestamp?.slice(11, 19) ?? '--:--:--'
            return (
              <div
                key={e.id ?? ts + Math.random().toString(36).slice(2)}
                style={{
                  display: 'flex',
                  gap: 6,
                  padding: '3px 0',
                  borderBottom: '1px solid rgba(0,212,255,0.03)',
                  fontSize: 9,
                  lineHeight: 1.4,
                }}
              >
                <span style={{ color: '#335566', flexShrink: 0, fontFamily: 'monospace' }}>
                  {ts}
                </span>
                <span style={{
                  color: eventTypeColor(e.event_type),
                  flexShrink: 0,
                  textTransform: 'uppercase',
                  fontSize: 8,
                  letterSpacing: '0.05em',
                }}>
                  [{e.event_type}]
                </span>
                <span style={{ color: '#8899aa', wordBreak: 'break-word' }}>
                  {e.content}
                </span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
