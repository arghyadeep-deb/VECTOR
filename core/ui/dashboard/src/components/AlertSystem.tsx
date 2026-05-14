import { useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import { Z } from '../lib/zIndex'

interface Alert {
  id: string
  zone: number
  content: ReactNode
  createdAt: number
}

const ZONE_CLASSES = ['top-left', 'top-center', 'top-right', 'bottom-left', 'bottom-center', 'bottom-right']

const ZONE_POSITIONS: Record<string, React.CSSProperties> = {
  'top-left': { top: 56, left: 210 },
  'top-center': { top: 56, left: '50%', marginLeft: -190 },
  'top-right': { top: 56, right: 200 },
  'bottom-left': { bottom: 80, left: 210 },
  'bottom-center': { bottom: 80, left: '50%', marginLeft: -190 },
  'bottom-right': { bottom: 80, right: 200 },
}

const MAX_VISIBLE = 3

let alertIdCounter = 0

export function useAlertSystem() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [occupied, setOccupied] = useState<Set<number>>(new Set())
  const queue = useRef<Alert[]>([])

  const spawnAlert = useCallback((content: ReactNode) => {
    const zone = (() => {
      for (let i = 0; i < 6; i++) {
        if (!occupied.has(i)) return i
      }
      const oldest = [...alerts, ...queue.current].sort((a, b) => a.createdAt - b.createdAt)[0]
      return oldest ? oldest.zone : 0
    })()

    const alert: Alert = { id: `alert-${++alertIdCounter}`, zone, content, createdAt: Date.now() }

    if (alerts.length >= MAX_VISIBLE) {
      queue.current.push(alert)
    } else {
      setAlerts((prev) => [...prev, alert])
      setOccupied((prev) => new Set(prev).add(zone))
    }

    setTimeout(() => {
      dismissAlert(alert.id)
    }, 6000)
  }, [alerts, occupied])

  const dismissAlert = useCallback((id: string) => {
    setAlerts((prev) => {
      const removed = prev.find((a) => a.id === id)
      if (removed) {
        setOccupied((occ) => {
          const next = new Set(occ)
          next.delete(removed.zone)
          return next
        })
      }
      const remaining = prev.filter((a) => a.id !== id)
      if (queue.current.length > 0 && remaining.length < MAX_VISIBLE) {
        const next = queue.current.shift()!
        setOccupied((occ) => new Set(occ).add(next.zone))
        return [...remaining, next]
      }
      return remaining
    })
  }, [])

  return { alerts, dismissAlert, spawnAlert }
}

export default function AlertSystem({ alerts, dismissAlert }: { alerts: Alert[]; dismissAlert: (id: string) => void }) {
  return (
    <>
      {alerts.map((alert) => {
        const zoneClass = ZONE_CLASSES[alert.zone]
        const pos = ZONE_POSITIONS[zoneClass]
        return (
          <AlertPanel key={alert.id} pos={pos} onClose={() => dismissAlert(alert.id)}>
            {alert.content}
          </AlertPanel>
        )
      })}
    </>
  )
}

function AlertPanel({ pos, onClose, children }: { pos: React.CSSProperties; onClose: () => void; children: ReactNode }) {
  const [progress, setProgress] = useState(100)
  const [exiting, setExiting] = useState(false)

  useEffect(() => {
    const start = Date.now()
    const dur = 6000
    let raf: number
    const tick = () => {
      const elapsed = Date.now() - start
      const pct = Math.max(0, 100 - (elapsed / dur) * 100)
      setProgress(pct)
      if (pct > 0) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  const handleClose = () => {
    setExiting(true)
    setTimeout(onClose, 200)
  }

  return (
    <div
      style={{
        position: 'fixed',
        zIndex: Z.ALERTS,
        width: 380,
        background: 'rgba(2, 18, 32, 0.95)',
        border: '1px solid #00CFFF',
        clipPath: 'polygon(10px 0%, 100% 0%, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0% 100%, 0% 10px)',
        boxShadow: '0 0 20px #00CFFF22, inset 0 0 30px #00CFFF08',
        animation: exiting ? 'fpExit 200ms ease forwards' : 'fpEnter 300ms ease forwards',
        ...pos,
      }}
    >
      <div style={{ position: 'relative' }}>
        {children}
        {/* Progress bar */}
        <div style={{ height: 2, background: 'rgba(0,207,255,0.05)' }}>
          <div style={{ width: `${progress}%`, height: '100%', background: '#00CFFF', transition: 'width 0.1s linear' }} />
        </div>
        {/* Close button */}
        <button
          onClick={handleClose}
          style={{
            position: 'absolute', top: 4, right: 6,
            background: 'transparent', border: 'none',
            color: '#3388aa', cursor: 'pointer',
            fontFamily: "'Orbitron', sans-serif", fontSize: 8,
          }}
        >✕</button>
      </div>
    </div>
  )
}
