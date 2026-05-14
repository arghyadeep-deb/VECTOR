import { useState, useEffect, useRef, type ReactNode } from 'react'

interface FloatingPanelProps {
  title: string
  subtitle?: string
  children: ReactNode
  style?: React.CSSProperties
  onClose?: () => void
  defaultOpen?: boolean
  autoDismiss?: number
}

let injected = false

export default function FloatingPanel({ title, subtitle, children, style, onClose, defaultOpen = true, autoDismiss }: FloatingPanelProps) {
  const [open, setOpen] = useState(defaultOpen)
  const [exiting, setExiting] = useState(false)
  const [countdown, setCountdown] = useState(autoDismiss ?? 0)
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  useEffect(() => {
    if (!injected) {
      injected = true
      const s = document.createElement('style')
      s.textContent = `@keyframes fpEnter{from{opacity:0;transform:scale(0.85)}to{opacity:1;transform:scale(1)}}@keyframes fpExit{from{opacity:1;transform:scale(1)}to{opacity:0;transform:scale(0.85)}}`
      document.head.appendChild(s)
    }
  }, [])

  useEffect(() => {
    if (autoDismiss && autoDismiss > 0) {
      setCountdown(autoDismiss)
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timerRef.current)
            handleClose()
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [autoDismiss])

  const handleClose = () => {
    setExiting(true)
    setTimeout(() => {
      setOpen(false)
      onClose?.()
    }, 200)
  }

  if (!open) return null

  return (
    <div
      style={{
        position: 'absolute',
        background: 'rgba(2, 18, 32, 0.92)',
        border: '1px solid #00CFFF',
        clipPath: 'polygon(10px 0%, 100% 0%, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0% 100%, 0% 10px)',
        boxShadow: '0 0 20px #00CFFF22, inset 0 0 30px #00CFFF08',
        animation: exiting
          ? 'fpExit 200ms cubic-bezier(0.23,1,0.32,1) forwards'
          : 'fpEnter 300ms cubic-bezier(0.23,1,0.32,1) forwards',
        ...style,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          borderBottom: '1px solid rgba(0,207,255,0.1)',
          fontFamily: "'Orbitron', sans-serif",
          fontSize: 9,
          color: '#3388aa',
          letterSpacing: '0.12em',
          textTransform: 'uppercase' as const,
        }}
      >
        <span>{title}{subtitle && <span style={{ color: '#004466', fontSize: 8, fontFamily: "'JetBrains Mono', monospace", marginLeft: 8 }}>{subtitle}</span>}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {autoDismiss && countdown > 0 && (
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#004466' }}>{countdown}s</span>
          )}
          {onClose && (
            <button
              onClick={handleClose}
              style={{
                background: 'transparent',
                border: '1px solid rgba(0,207,255,0.15)',
                color: '#3388aa',
                fontFamily: "'Orbitron', sans-serif",
                fontSize: 8,
                cursor: 'pointer',
                padding: '2px 6px',
                lineHeight: 1,
                letterSpacing: '0.05em',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.color = '#00CFFF'; e.currentTarget.style.borderColor = 'rgba(0,207,255,0.35)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = '#3388aa'; e.currentTarget.style.borderColor = 'rgba(0,207,255,0.15)' }}
            >
              ✕
            </button>
          )}
        </div>
      </div>
      {children}
    </div>
  )
}
