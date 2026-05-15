import { useRef, useEffect } from 'react'
import { Z } from '../lib/zIndex'

const SIZE = 100

export default function RadarWidget() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const cvs = canvasRef.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')
    if (!ctx) return

    let angle = 0
    let rafId = 0

    const draw = () => {
      const size = SIZE * 2
      ctx.clearRect(0, 0, size, size)

      const cx = size / 2
      const cy = size / 2
      const r = size / 2 - 2

      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(0,207,255,0.15)'
      ctx.lineWidth = 1
      ctx.stroke()

      for (let i = 1; i <= 3; i++) {
        ctx.beginPath()
        ctx.arc(cx, cy, r * (i / 3), 0, Math.PI * 2)
        ctx.strokeStyle = 'rgba(0,207,255,0.08)'
        ctx.stroke()
      }

      ctx.beginPath()
      ctx.moveTo(cx - r, cy)
      ctx.lineTo(cx + r, cy)
      ctx.moveTo(cx, cy - r)
      ctx.lineTo(cx, cy + r)
      ctx.strokeStyle = 'rgba(0,207,255,0.1)'
      ctx.stroke()

      const sweepAngle = angle * (Math.PI / 180)
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.arc(cx, cy, r, sweepAngle - 0.4, sweepAngle)
      ctx.fillStyle = 'rgba(0,207,255,0.12)'
      ctx.fill()

      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(cx + Math.cos(sweepAngle) * r, cy + Math.sin(sweepAngle) * r)
      ctx.strokeStyle = 'rgba(0,207,255,0.5)'
      ctx.lineWidth = 1.5
      ctx.stroke()

      const blipAngle = (angle + 120) * (Math.PI / 180)
      const blipR = r * 0.6
      const bx = cx + Math.cos(blipAngle) * blipR
      const by = cy + Math.sin(blipAngle) * blipR
      ctx.beginPath()
      ctx.arc(bx, by, 2, 0, Math.PI * 2)
      ctx.fillStyle = '#4FC3F7'
      ctx.fill()

      angle = (angle + 1.5) % 360
      rafId = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(rafId)
  }, [])

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 42,
        left: 10,
        zIndex: Z.CORNER_HUD,
        pointerEvents: 'none',
      }}
    >
      <canvas
        ref={canvasRef}
        width={SIZE * 2}
        height={SIZE * 2}
        style={{
          width: SIZE,
          height: SIZE,
          opacity: 0.7,
        }}
      />
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 7,
          color: '#004466',
          letterSpacing: '0.12em',
          textAlign: 'center',
          marginTop: 2,
        }}
      >
        RADAR
      </div>
    </div>
  )
}
