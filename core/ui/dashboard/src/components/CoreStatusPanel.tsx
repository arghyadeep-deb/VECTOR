import { useState, useRef, useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { formatUptime } from '../lib/api'
import { Z } from '../lib/zIndex'

export default function CoreStatusPanel() {
  const status = useVectorStore((s) => s.status)
  const [minimized, setMinimized] = useState(false)
  const [dragPos, setDragPos] = useState({ x: 244, y: 45 })
  const dragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const posStart = useRef({ x: 0, y: 0 })
  const [uptimeOffset, setUptimeOffset] = useState(0)
  const [cycles] = useState(42)
  const [reflectionTime, setReflectionTime] = useState('')

  useEffect(() => {
    if (status?.uptime_seconds) {
      setUptimeOffset(0)
    }
    const id = setInterval(() => {
      setUptimeOffset((p) => p + 1)
      const now = new Date()
      const target = new Date(now)
      target.setHours(2, 0, 0, 0)
      if (now > target) target.setDate(target.getDate() + 1)
      const diff = Math.round((target.getTime() - now.getTime()) / 1000)
      const h = Math.floor(diff / 3600)
      const m = Math.floor((diff % 3600) / 60)
      setReflectionTime(`${h}h ${m}m`)
    }, 1000)
    return () => clearInterval(id)
  }, [])

  const handleMouseDown = (e: React.MouseEvent) => {
    dragging.current = true
    dragStart.current = { x: e.clientX, y: e.clientY }
    posStart.current = { x: dragPos.x, y: dragPos.y }
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }

  const handleMouseMove = (e: MouseEvent) => {
    if (!dragging.current) return
    setDragPos({
      x: posStart.current.x + (e.clientX - dragStart.current.x),
      y: posStart.current.y + (e.clientY - dragStart.current.y),
    })
  }

  const handleMouseUp = () => {
    dragging.current = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
  }

  return (
    <div
      style={{
        width: '100%',
        background: 'rgba(2, 18, 32, 0.92)',
        border: '1px solid rgba(0,207,255,0.2)',
        clipPath: 'polygon(10px 0%, 100% 0%, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0% 100%, 0% 10px)',
        boxShadow: '0 0 20px #00CFFF22, inset 0 0 30px #00CFFF08',
      }}
    >
      {/* Header (draggable) */}
      <div
        onMouseDown={handleMouseDown}
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '4px 8px', cursor: 'grab',
          borderBottom: minimized ? 'none' : '1px solid rgba(0,207,255,0.1)',
          fontFamily: "'Orbitron', sans-serif", fontSize: 7,
          color: '#3388aa', letterSpacing: '0.12em', textTransform: 'uppercase',
          userSelect: 'none',
        }}
      >
        <span>CORE STATUS</span>
        <button
          onClick={() => setMinimized(!minimized)}
          style={{
            background: 'transparent', border: '1px solid rgba(0,207,255,0.15)',
            color: '#3388aa', cursor: 'pointer', padding: '1px 5px',
            fontFamily: "'Orbitron', sans-serif", fontSize: 7,
          }}
        >
          {minimized ? '□' : '–'}
        </button>
      </div>

      {!minimized && (
        <div style={{ padding: '6px 8px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {/* Mini arc reactor SVG */}
          <svg viewBox="0 0 60 60" style={{ width: 60, height: 60, alignSelf: 'center' }}>
            <circle cx={30} cy={30} r={28} fill="none" stroke="rgba(0,207,255,0.1)" strokeWidth={1}>
              <animateTransform attributeName="transform" type="rotate" from="0 30 30" to="360 30 30" dur="8s" repeatCount="indefinite" />
            </circle>
            <circle cx={30} cy={30} r={20} fill="none" stroke="rgba(0,207,255,0.15)" strokeWidth={1}>
              <animateTransform attributeName="transform" type="rotate" from="360 30 30" to="0 30 30" dur="5s" repeatCount="indefinite" />
            </circle>
            <circle cx={30} cy={30} r={10} fill="none" stroke="rgba(0,207,255,0.2)" strokeWidth={1}>
              <animateTransform attributeName="transform" type="rotate" from="0 30 30" to="360 30 30" dur="3s" repeatCount="indefinite" />
            </circle>
            <circle cx={30} cy={30} r={3} fill="#00CFFF" opacity={0.6}>
              <animate attributeName="r" values="2;4;2" dur="1.5s" repeatCount="indefinite" />
            </circle>
          </svg>

          {/* Stats */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Row label="UPTIME" value={formatUptime((status?.uptime_seconds ?? 0) + uptimeOffset)} />
            <Row label="CYCLES" value={(cycles + uptimeOffset).toString()} />
            <Row label="REFLECT" value={reflectionTime} />
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a4466', letterSpacing: '0.12em' }}>
        {label}
      </span>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#00CFFF' }}>
        {value}
      </span>
    </div>
  )
}
