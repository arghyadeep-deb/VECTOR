import { useState, useEffect } from 'react'
import { api } from '../lib/api'

const CYAN = '#00CFFF'

export default function VectorTopBar() {
  const [time, setTime] = useState('')
  const [dots, setDots] = useState({ loop: false, ollama: false, memory: false, gateway: true })

  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('en-US', { hour12: false }))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const check = async () => {
      try {
        const s = await api.status()
        setDots({
          loop: s.loop_running ?? false,
          ollama: !!(s.models),
          memory: (s.memory?.episodic_memory ?? 0) > 0,
          gateway: true,
        })
      } catch {}
    }
    check()
    const id = setInterval(check, 15000)
    return () => clearInterval(id)
  }, [])

  const statusDots = [
    { label: 'LOOP',    ok: dots.loop },
    { label: 'OLLAMA',  ok: dots.ollama },
    { label: 'MEM',     ok: dots.memory },
    { label: 'GATE',    ok: dots.gateway },
  ]

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0,
      height: 32,
      background: 'rgba(0,0,0,0.85)',
      borderBottom: '1px solid rgba(0,207,255,0.08)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 16px',
      zIndex: 50,
      backdropFilter: 'blur(4px)',
    }}>
      {/* Left: VECTOR branding */}
      <span style={{
        fontFamily: "'Orbitron', sans-serif",
        fontSize: 13,
        fontWeight: 700,
        color: CYAN,
        letterSpacing: '0.35em',
        filter: 'drop-shadow(0 0 6px #00CFFF88)',
      }}>
        VECTOR
      </span>

      {/* Center: clock */}
      <span style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
        color: 'rgba(0,207,255,0.4)',
        letterSpacing: '0.15em',
      }}>
        {time}
      </span>

      {/* Right: status dots */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        {statusDots.map(({ label, ok }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{
              width: 5, height: 5, borderRadius: '50%',
              background: ok ? '#00FF88' : '#FF3355',
              boxShadow: ok ? '0 0 4px #00FF88' : '0 0 4px #FF3355',
            }} />
            <span style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 7.5,
              color: 'rgba(0,207,255,0.35)',
              letterSpacing: '0.1em',
            }}>
              {label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
