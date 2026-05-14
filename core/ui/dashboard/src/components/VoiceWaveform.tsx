import { useRef, useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

const BAR_COUNT = 48
const BAR_W = 2.5
const GAP = 1.5
const H = 28

export default function VoiceWaveform() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const status = useVectorStore((s) => s.status)
  const isOnline = !!status

  useEffect(() => {
    const cvs = canvasRef.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')
    if (!ctx) return

    let t = 0
    let rafId = 0

    const draw = () => {
      const w = cvs.width
      const h = cvs.height
      ctx.clearRect(0, 0, w, h)

      const totalW = BAR_COUNT * (BAR_W + GAP)
      const startX = (w - totalW) / 2

      for (let i = 0; i < BAR_COUNT; i++) {
        const norm = i / BAR_COUNT
        const distCenter = Math.abs(norm - 0.5) * 2

        // Multi-frequency waveform — more organic, JARVIS-like
        const wave1 = Math.sin(t * 0.04 + i * 0.35) * 0.45
        const wave2 = Math.sin(t * 0.07 + i * 0.6) * 0.25
        const wave3 = Math.sin(t * 0.12 + i * 0.9) * 0.15
        const combined = (wave1 + wave2 + wave3 + 0.85) * H * (1 - distCenter * 0.4)

        const barH = Math.max(2, combined)
        const x = startX + i * (BAR_W + GAP)
        const y = (h - barH) / 2

        // Color: teal-cyan gradient, brighter at center
        const intensity = barH / H
        const alpha = isOnline ? (0.25 + intensity * 0.65) : (0.08 + intensity * 0.12)
        const color = isOnline
          ? `rgba(0, ${Math.floor(200 + intensity * 55)}, ${Math.floor(200 + intensity * 55)}, ${alpha})`
          : `rgba(30, 80, 100, ${alpha})`

        ctx.fillStyle = color

        // Rounded bars
        const radius = BAR_W / 2
        ctx.beginPath()
        ctx.moveTo(x + radius, y)
        ctx.lineTo(x + BAR_W - radius, y)
        ctx.quadraticCurveTo(x + BAR_W, y, x + BAR_W, y + radius)
        ctx.lineTo(x + BAR_W, y + barH - radius)
        ctx.quadraticCurveTo(x + BAR_W, y + barH, x + BAR_W - radius, y + barH)
        ctx.lineTo(x + radius, y + barH)
        ctx.quadraticCurveTo(x, y + barH, x, y + barH - radius)
        ctx.lineTo(x, y + radius)
        ctx.quadraticCurveTo(x, y, x + radius, y)
        ctx.closePath()
        ctx.fill()
      }

      t++
      rafId = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(rafId)
  }, [isOnline])

  const totalW = BAR_COUNT * (BAR_W + GAP) + 20

  return (
    <div style={{
      position: 'fixed',
      bottom: 10,
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: Z.VOICE,
      pointerEvents: 'none',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 3,
    }}>
      <canvas
        ref={canvasRef}
        width={totalW}
        height={H + 8}
        style={{ width: totalW, height: H + 8 }}
      />
      {/* Status label */}
      <div style={{
        fontFamily: "'Orbitron', sans-serif",
        fontSize: 7,
        letterSpacing: '0.2em',
        color: isOnline ? 'rgba(0,255,212,0.5)' : 'rgba(0,100,140,0.4)',
        textTransform: 'uppercase',
      }}>
        {isOnline ? '● VOICE ACTIVE' : '○ STANDBY'}
      </div>
    </div>
  )
}
