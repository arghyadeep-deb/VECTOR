import { useEffect, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'

type BootPhase = 'black' | 'border_faint' | 'border_bright' | 'scanline' | 'orb_in' | 'done'

export default function BootSequence() {
  const bootDone = useVectorStore((s) => s.bootDone)
  const setBootDone = useVectorStore((s) => s.setBootDone)
  const [phase, setPhase] = useState<BootPhase>('black')
  const [scanY, setScanY] = useState(0)
  const [scanOpacity, setScanOpacity] = useState(1)

  useEffect(() => {
    if (bootDone) return

    const t = (delay: number, fn: () => void) => setTimeout(fn, delay)

    const ids = [
      t(200,  () => setPhase('border_faint')),
      t(700,  () => setPhase('border_bright')),
      t(1100, () => { setPhase('scanline'); setScanY(0) }),
      t(2700, () => { setScanOpacity(0) }),
      t(3000, () => { setPhase('orb_in') }),
      t(3600, () => { setPhase('done'); setBootDone(true) }),
    ]

    // Animate scan line from top to bottom over 1.5s (starting at t=1100)
    let scanStart: number | null = null
    let rafId: number
    const phaseRef = { current: phase }
    const animateScan = (ts: number) => {
      if (phaseRef.current !== 'scanline') {
        cancelAnimationFrame(rafId)
        return
      }
      if (!scanStart) scanStart = ts
      const elapsed = ts - scanStart
      const progress = Math.min(elapsed / 1500, 1)
      setScanY(progress * 100)
      if (progress < 1) rafId = requestAnimationFrame(animateScan)
    }

    t(1100, () => { scanStart = null; rafId = requestAnimationFrame(animateScan) })

    return () => {
      ids.forEach(clearTimeout)
      cancelAnimationFrame(rafId)
    }
  }, [bootDone])

  if (bootDone) return null

  return (
    <>
      {/* Full-screen black overlay — fades out in orb_in phase */}
      <div style={{
        position: 'fixed',
        inset: 0,
        background: '#000',
        zIndex: 9998,
        opacity: phase === 'orb_in' ? 0 : 1,
        transition: phase === 'orb_in' ? 'opacity 0.6s ease' : 'none',
        pointerEvents: phase === 'orb_in' ? 'none' : 'all',
      }} />

      {/* Sharp border — only during border_bright and scanline phases (not gradient, just a line) */}
      {(phase === 'border_bright' || phase === 'scanline') && (
        <div style={{
          position: 'fixed',
          inset: 0,
          border: '2px solid #00CFFF',
          zIndex: 9999,
          pointerEvents: 'none',
        }} />
      )}

      {/* Scan line */}
      {(phase === 'scanline') && (
        <div style={{
          position: 'fixed',
          left: 0,
          right: 0,
          top: `${scanY}vh`,
          height: 2,
          background: 'linear-gradient(90deg, transparent 0%, rgba(0,207,255,0.3) 10%, #00CFFF 50%, rgba(0,207,255,0.3) 90%, transparent 100%)',
          boxShadow: '0 0 20px #00CFFF, 0 0 40px rgba(0,207,255,0.6)',
          zIndex: 9999,
          opacity: scanOpacity,
          transition: 'opacity 0.3s ease',
          pointerEvents: 'none',
        }} />
      )}

      {/* Horizontal reflection line below scan */}
      {(phase === 'scanline') && (
        <div style={{
          position: 'fixed',
          left: 0,
          right: 0,
          top: `${scanY}vh`,
          height: 40,
          background: 'linear-gradient(180deg, rgba(0,207,255,0.08) 0%, transparent 100%)',
          zIndex: 9999,
          opacity: scanOpacity,
          transition: 'opacity 0.3s ease',
          pointerEvents: 'none',
        }} />
      )}
    </>
  )
}
