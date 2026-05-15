import { useRef, useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

interface Star {
  x: number; y: number; size: number; speed: number; alpha: number; driftX: number; driftY: number
}

export default function BackgroundCanvas() {
  const ref = useRef<HTMLCanvasElement>(null)
  const starsRef = useRef<Star[]>([])
  const moodRef = useRef('#4FC3F7')
  useVectorStore((s) => {
    moodRef.current = getComputedStyle(document.documentElement).getPropertyValue('--theme-accent').trim() || '#4FC3F7'
  })

  useEffect(() => {
    const cvs = ref.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')
    if (!ctx) return

    const resize = () => {
      cvs.width = window.innerWidth
      cvs.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    const count = 400
    starsRef.current = Array.from({ length: count }, (_, i) => ({
      x: Math.random() * cvs.width,
      y: Math.random() * cvs.height,
      size: i % 5 === 0 ? 1 + Math.random() * 0.8 : 0.2 + Math.random() * 0.6,
      speed: 0.03 + Math.random() * 0.12,
      alpha: i % 5 === 0 ? 0.4 + Math.random() * 0.4 : 0.1 + Math.random() * 0.3,
      driftX: (Math.random() - 0.5) * 0.2,
      driftY: (Math.random() - 0.5) * 0.2,
    }))

    let raf = 0
    const draw = () => {
      ctx.clearRect(0, 0, cvs.width, cvs.height)
      const accent = moodRef.current

      for (const s of starsRef.current) {
        s.x += s.driftX * s.speed
        s.y += s.driftY * s.speed
        if (s.x < 0) s.x = cvs.width
        if (s.x > cvs.width) s.x = 0
        if (s.y < 0) s.y = cvs.height
        if (s.y > cvs.height) s.y = 0

        const pulse = 0.7 + 0.3 * Math.sin(Date.now() * 0.001 * s.speed + s.x)
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2)
        ctx.fillStyle = accent || '#4FC3F7'
        ctx.globalAlpha = s.alpha * pulse
        ctx.fill()
      }
      ctx.globalAlpha = 1
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) }
  }, [])

  return (
    <canvas
      ref={ref}
      style={{ position: 'fixed', inset: 0, zIndex: Z.BACKGROUND, pointerEvents: 'none' }}
    />
  )
}