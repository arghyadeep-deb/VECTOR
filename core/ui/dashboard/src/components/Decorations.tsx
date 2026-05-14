import { useRef, useEffect } from 'react'
import BackgroundGrid from './BackgroundGrid'
import { Z } from '../lib/zIndex'

const RING_COUNT = 6
const COLORS = ['#00CFFF', '#00AACC', '#006688', '#004466', '#002244', '#001133']

function ConcentricRings() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const cvs = canvasRef.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')
    if (!ctx) return

    let anim = 0
    let rafId = 0

    const draw = () => {
      const w = cvs.width
      const h = cvs.height
      const cx = w / 2
      const cy = h / 2
      const maxR = Math.min(w, h) * 0.45

      ctx.clearRect(0, 0, w, h)

      for (let i = 0; i < RING_COUNT; i++) {
        const phase = (anim * 0.008 + i / RING_COUNT) % 1
        const radius = maxR * (0.15 + phase * 0.85)
        const opacity = 1 - phase

        ctx.beginPath()
        ctx.arc(cx, cy, radius, 0, Math.PI * 2)
        ctx.strokeStyle = COLORS[i % COLORS.length]
        ctx.globalAlpha = opacity * 0.25
        ctx.lineWidth = 1
        ctx.stroke()
      }

      ctx.globalAlpha = 1
      anim++
      rafId = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(rafId)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      width={window.innerWidth}
      height={window.innerHeight}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: Z.DECORATIONS,
        pointerEvents: 'none',
        opacity: 0.4,
      }}
    />
  )
}

function Vignette() {
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: Z.DECORATIONS,
        pointerEvents: 'none',
        background: 'radial-gradient(circle at center, transparent 40%, rgba(0,0,0,0.6) 100%)',
      }}
    />
  )
}

export default function Decorations() {
  return (
    <>
      <BackgroundGrid />
      <ConcentricRings />
      <Vignette />
    </>
  )
}
