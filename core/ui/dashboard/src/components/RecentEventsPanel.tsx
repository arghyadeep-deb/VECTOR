import { useState, useEffect } from 'react'

const API = window.location.origin

interface Event { event_type?: string; type?: string; content?: string; timestamp?: string; ts?: string; source?: string }

export default function RecentEventsPanel() {
  const [events, setEvents] = useState<Event[]>([])
  const [total, setTotal] = useState(0)

  useEffect(() => {
    const poll = async () => {
      try {
        const r = await fetch(`${API}/ui/memory`, { credentials: 'include' })
        if (r.ok) {
          const d = await r.json()
          setTotal(d.total_events || d.count || d.events?.length || 0)
        }
      } catch {}
      try {
        const r = await fetch(`${API}/memory/recent?limit=8`, { credentials: 'include' })
        if (r.ok) {
          const d = await r.json()
          setEvents((d.events || d || []).slice(0, 8))
        }
      } catch {}
    }
    poll(); const id = setInterval(poll, 8000)
    return () => clearInterval(id)
  }, [])

  const fmt = (e: Event) => {
    const t = e.timestamp || e.ts || ''
    const time = t ? t.slice(11, 19) : ''
    const type = (e.event_type || e.type || 'event').toLowerCase()
    let content = (e.content || '').slice(0, 70)
    if (content.length >= 70) content += '...'
    return { time, type, content }
  }

  return (
    <div style={{
      position: 'fixed', right: 0, bottom: 12, width: 220,
      background: 'rgba(0,8,20,0.88)', border: '1px solid rgba(0,212,255,0.2)',
      borderRadius: 6, padding: '6px 10px', zIndex: 48,
      fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: '#888',
      maxHeight: 160, overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        borderBottom: '1px solid rgba(0,212,255,0.12)', paddingBottom: 3, marginBottom: 4,
      }}>
        <span style={{ color: '#4FC3F7', fontSize: 8, letterSpacing: 1.5, textTransform: 'uppercase' }}>
          EVENT LOG
        </span>
        <span style={{ color: '#81D4FA', fontSize: 8 }}>{total} total</span>
      </div>
      {events.length === 0 ? (
        <div style={{ color: '#444', fontStyle: 'italic' }}>awaiting events...</div>
      ) : (
        events.map((e, i) => {
          const { time, type, content } = fmt(e)
          const color = type.includes('error') || type.includes('fail') ? '#FF3D3D'
            : type.includes('act') || type.includes('dispatch') ? '#81D4FA'
            : type.includes('decide') || type.includes('council') ? '#64B5F6'
            : type.includes('memory') || type.includes('store') ? '#42A5F5'
            : '#888'
          return (
            <div key={i} style={{
              display: 'flex', gap: 4, padding: '1px 0',
              borderBottom: i < events.length - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none',
            }}>
              <span style={{ color: '#555', width: 48, flexShrink: 0 }}>{time}</span>
              <span style={{ color, width: 48, flexShrink: 0, textTransform: 'uppercase' }}>{type.slice(0, 8)}</span>
              <span style={{ color: '#999', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {content}
              </span>
            </div>
          )
        })
      )}
    </div>
  )
}
