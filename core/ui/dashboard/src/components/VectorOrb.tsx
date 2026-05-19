import { useEffect, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'

export default function VectorOrb() {
  const orbInCorner = useVectorStore((s) => s.orbInCorner)
  const status = useVectorStore((s) => s.status)
  const [pulse, setPulse] = useState(false)
  const [time, setTime] = useState('')

  // Clock — only shown when orb is centered (idle state)
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      const h = now.getHours().toString().padStart(2, '0')
      const m = now.getMinutes().toString().padStart(2, '0')
      const s = now.getSeconds().toString().padStart(2, '0')
      setTime(`${h}:${m}:${s}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  // Pulse animation every 3s
  useEffect(() => {
    const id = setInterval(() => {
      setPulse(true)
      setTimeout(() => setPulse(false), 800)
    }, 3000)
    return () => clearInterval(id)
  }, [])

  const isOnline = status?.loop_running ?? false

  const containerStyle: React.CSSProperties = orbInCorner
    ? {
        position: 'fixed',
        bottom: 24,
        right: 24,
        width: 80,
        height: 80,
        zIndex: 200,
        transition: 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)',
        cursor: 'pointer',
      }
    : {
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 200,
        height: 200,
        zIndex: 200,
        transition: 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)',
      }

  const size = orbInCorner ? 80 : 200
  const fontSize = orbInCorner ? 9 : 18
  const glowIntensity = pulse ? '0 0 60px #00CFFF, 0 0 120px rgba(0,207,255,0.5), inset 0 0 60px rgba(0,207,255,0.15)' : '0 0 40px #00CFFF, 0 0 80px rgba(0,207,255,0.3), inset 0 0 40px rgba(0,207,255,0.08)'

  return (
    <>
      <div style={containerStyle}>
        {/* Outer ring */}
        <div style={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          border: `${orbInCorner ? 2 : 3}px solid #00CFFF`,
          boxShadow: glowIntensity,
          animation: 'orbRotate 8s linear infinite',
          transition: 'box-shadow 0.8s ease',
        }} />

        {/* Inner glow fill */}
        <div style={{
          position: 'absolute',
          inset: orbInCorner ? 8 : 20,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0,207,255,0.06) 0%, transparent 70%)',
          animation: 'orbPulseInner 3s ease-in-out infinite',
        }} />

        {/* Center content */}
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: orbInCorner ? 1 : 4,
        }}>
          <span style={{
            fontFamily: "'Orbitron', sans-serif",
            fontSize,
            fontWeight: 700,
            color: '#00CFFF',
            letterSpacing: '0.15em',
            textShadow: '0 0 20px rgba(0,207,255,0.8)',
            transition: 'font-size 0.6s ease',
          }}>
            VECTOR
          </span>
          {!orbInCorner && (
            <span style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11,
              color: 'rgba(0,207,255,0.5)',
              letterSpacing: '0.1em',
            }}>
              {isOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          )}
        </div>

        {/* Tick marks around ring — only when centered */}
        {!orbInCorner && (
          <svg style={{ position: 'absolute', inset: -10, width: size + 20, height: size + 20 }} viewBox={`0 0 ${size + 20} ${size + 20}`}>
            {Array.from({ length: 36 }).map((_, i) => {
              const angle = (i * 10 * Math.PI) / 180
              const cx = (size + 20) / 2
              const cy = (size + 20) / 2
              const r1 = size / 2 + 2
              const r2 = i % 3 === 0 ? size / 2 + 10 : size / 2 + 6
              const x1 = cx + r1 * Math.cos(angle)
              const y1 = cy + r1 * Math.sin(angle)
              const x2 = cx + r2 * Math.cos(angle)
              const y2 = cy + r2 * Math.sin(angle)
              return (
                <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="#00CFFF"
                  strokeWidth={i % 3 === 0 ? 1.5 : 0.8}
                  opacity={i % 3 === 0 ? 0.6 : 0.25}
                />
              )
            })}
          </svg>
        )}
      </div>

      {/* Clock + status — only in idle (centered) mode */}
      {!orbInCorner && (
        <div style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, calc(-50% + 120px))',
          textAlign: 'center',
          zIndex: 199,
          pointerEvents: 'none',
        }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 32,
            color: '#00CFFF',
            letterSpacing: '0.12em',
            textShadow: '0 0 30px rgba(0,207,255,0.6)',
            lineHeight: 1,
          }}>
            {time}
          </div>
          <div style={{
            fontFamily: "'Orbitron', sans-serif",
            fontSize: 9,
            color: 'rgba(0,207,255,0.35)',
            letterSpacing: '0.2em',
            marginTop: 8,
          }}>
            VECTOR · COGNITIVE ENGINE
          </div>
        </div>
      )}

      <style>{`
        @keyframes orbRotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes orbPulseInner {
          0%, 100% { opacity: 0.4; transform: scale(1); }
          50% { opacity: 0.8; transform: scale(1.05); }
        }
      `}</style>
    </>
  )
}
