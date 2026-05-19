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
  const voiceState = useVectorStore((s) => s.voiceState)
  const audioLevel = useVectorStore((s) => s.audioLevel)
  const isOnline = !!status

  // Kokoro warning from status models field
  const ttsEngine = (status?.models as any)?.tts_engine as string | undefined
  const kokoroMissing = ttsEngine === 'pyttsx3'

  // Amplitude multiplier per voice state
  const ampByState: Record<string, number> = {
    idle: 0.35,
    listening: 1.0,   // full amplitude — user is speaking
    processing: 0.55, // medium pulse while thinking
    speaking: 0.80,   // VECTOR is speaking
  }

  // Speed multiplier per voice state
  const speedByState: Record<string, number> = {
    idle: 1.0,
    listening: 2.2,
    processing: 1.5,
    speaking: 1.8,
  }

  const ampRef = useRef(ampByState[voiceState] ?? 0.35)
  const speedRef = useRef(speedByState[voiceState] ?? 1.0)
  const voiceStateRef = useRef(voiceState)
  const audioLevelRef = useRef(audioLevel)

  // Update refs without restarting canvas loop
  useEffect(() => {
    ampRef.current = ampByState[voiceState] ?? 0.35
    speedRef.current = speedByState[voiceState] ?? 1.0
  }, [voiceState])

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

      const amp = ampRef.current
      const speed = speedRef.current
      const totalW = BAR_COUNT * (BAR_W + GAP)
      const startX = (w - totalW) / 2

      for (let i = 0; i < BAR_COUNT; i++) {
        const norm = i / BAR_COUNT
        const distCenter = Math.abs(norm - 0.5) * 2

        const wave1 = Math.sin(t * 0.04 * speed + i * 0.35) * 0.45
        const wave2 = Math.sin(t * 0.07 * speed + i * 0.6) * 0.25
        const wave3 = Math.sin(t * 0.12 * speed + i * 0.9) * 0.15
        const procBase = (wave1 + wave2 + wave3 + 0.85) * (1 - distCenter * 0.4)
        // Listening: use real mic amplitude; other states use procedural sine
        const realAmp = voiceState === 'listening' && audioLevel > 0
          ? audioLevel * (0.7 + 0.3 * Math.abs(Math.sin(t * 0.1 + i * 0.5)))
          : procBase * amp
        const barH = Math.max(2, realAmp * H)

        const x = startX + i * (BAR_W + GAP)
        const y = (h - barH) / 2

        const intensity = barH / H
        let alpha: number
        let color: string

        if (!isOnline) {
          alpha = 0.08 + intensity * 0.12
          color = `rgba(30,80,100,${alpha})`
        } else if (voiceState === 'listening') {
          alpha = 0.4 + intensity * 0.6
          color = `rgba(0,255,180,${alpha})`  // green-teal: mic active
        } else if (voiceState === 'speaking') {
          alpha = 0.35 + intensity * 0.55
          color = `rgba(0,220,255,${alpha})`  // cyan: VECTOR speaking
        } else if (voiceState === 'processing') {
          alpha = 0.2 + intensity * 0.4
          color = `rgba(100,180,255,${alpha})` // blue: thinking
        } else {
          alpha = 0.15 + intensity * 0.35
          color = `rgba(0,${Math.floor(180 + intensity * 75)},${Math.floor(180 + intensity * 75)},${alpha})`
        }

        ctx.fillStyle = color
        const r = BAR_W / 2
        ctx.beginPath()
        ctx.moveTo(x + r, y)
        ctx.lineTo(x + BAR_W - r, y)
        ctx.quadraticCurveTo(x + BAR_W, y, x + BAR_W, y + r)
        ctx.lineTo(x + BAR_W, y + barH - r)
        ctx.quadraticCurveTo(x + BAR_W, y + barH, x + BAR_W - r, y + barH)
        ctx.lineTo(x + r, y + barH)
        ctx.quadraticCurveTo(x, y + barH, x, y + barH - r)
        ctx.lineTo(x, y + r)
        ctx.quadraticCurveTo(x, y, x + r, y)
        ctx.closePath()
        ctx.fill()
      }

      t++
      rafId = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(rafId)
  }, [isOnline])  // canvas loop starts once; voiceState drives via refs

  const totalW = BAR_COUNT * (BAR_W + GAP) + 20

  const stateLabel: Record<string, string> = {
    idle: isOnline ? '● STANDBY' : '○ OFFLINE',
    listening: '◉ LISTENING',
    processing: '⟳ PROCESSING',
    speaking: '▶ SPEAKING',
  }

  const stateColor: Record<string, string> = {
    idle: isOnline ? 'rgba(0,200,160,0.45)' : 'rgba(0,100,140,0.4)',
    listening: 'rgba(0,255,160,0.9)',
    processing: 'rgba(100,180,255,0.8)',
    speaking: 'rgba(0,220,255,0.9)',
  }

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
      <div style={{
        fontFamily: "'Orbitron', sans-serif",
        fontSize: 7,
        letterSpacing: '0.2em',
        color: stateColor[voiceState] ?? stateColor.idle,
        textTransform: 'uppercase',
        transition: 'color 0.3s ease',
      }}>
        {stateLabel[voiceState] ?? stateLabel.idle}
      </div>
      {/* Kokoro warning — only shown when TTS falls back to pyttsx3 */}
      {kokoroMissing && (
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 7,
          color: 'rgba(255,170,0,0.7)',
          letterSpacing: '0.08em',
        }}>
          TTS: pyttsx3 fallback — install Kokoro for better voice
        </div>
      )}
    </div>
  )
}
