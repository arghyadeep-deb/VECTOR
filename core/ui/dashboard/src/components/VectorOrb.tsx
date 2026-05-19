import { useEffect, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'

export default function VectorOrb() {
  const orbInCorner = useVectorStore((s) => s.orbInCorner)
  const status = useVectorStore((s) => s.status)
  const voiceState = useVectorStore((s) => s.voiceState)
  const setVoiceState = useVectorStore((s) => s.setVoiceState)
  const [time, setTime] = useState('')
  const [pulse, setPulse] = useState(false)

  // Click: focus the command input so user can type or use voice
  const handleOrbClick = () => {
    const input = document.querySelector('input[placeholder]') as HTMLInputElement | null
    if (input) {
      input.focus()
      input.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(
        `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`
      )
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const id = setInterval(() => {
      setPulse(true)
      setTimeout(() => setPulse(false), 900)
    }, 3000)
    return () => clearInterval(id)
  }, [])

  const isOnline = status?.loop_running ?? false
  // voiceState drives animation speed and glow intensity
  const isListening = voiceState === 'listening'
  const isSpeaking = voiceState === 'speaking'
  const isVoiceProcessing = voiceState === 'processing'

  const arcSpinDuration = isListening ? '1.2s' : isSpeaking ? '2s' : '3s'
  const haloOpacity = isListening ? 0.12 : isSpeaking ? 0.10 : 0.04
  const ringOpacity = isListening ? 0.55 : isVoiceProcessing ? 0.4 : 0.28
  const arcOpacity = isListening ? 1.0 : isSpeaking ? 0.85 : 0.95

  const sz = orbInCorner ? 90 : 150
  const cx = sz / 2
  const cy = sz / 2
  const R = orbInCorner ? 34 : 60      // main ring radius
  const C = 2 * Math.PI * R            // circumference

  // Arc: ~110° bright; shorter when speaking (flicker effect)
  const arcLen = isSpeaking ? C * 0.18 : C * 0.31
  const gapLen = C - arcLen

  const containerStyle: React.CSSProperties = orbInCorner
    ? {
        position: 'fixed',
        bottom: 24,
        right: 24,
        width: sz,
        height: sz,
        zIndex: 200,
        cursor: 'pointer',
        transition: 'all 0.65s cubic-bezier(0.4,0,0.2,1)',
      }
    : {
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: sz,
        height: sz,
        zIndex: 200,
        transition: 'all 0.65s cubic-bezier(0.4,0,0.2,1)',
      }

  return (
    <>
      <div style={containerStyle} onClick={handleOrbClick} title="Click to open command input">
        <svg
          width={sz}
          height={sz}
          viewBox={`0 0 ${sz} ${sz}`}
          style={{ position: 'absolute', inset: 0, overflow: 'visible' }}
        >
          <defs>
            {/* Glow filter for the bright arc */}
            <filter id="arcGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation={orbInCorner ? 2 : 4} result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            {/* Outer halo glow */}
            <filter id="haloGlow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation={orbInCorner ? 4 : 12} result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
              </feMerge>
            </filter>
          </defs>

          {/* ── Outer halo ring — reacts to voice state */}
          <circle
            cx={cx} cy={cy}
            r={R + (orbInCorner ? 7 : 18)}
            fill="none"
            stroke={isListening ? '#00FFFF' : '#00CFFF'}
            strokeWidth={orbInCorner ? 8 : 22}
            opacity={haloOpacity}
            filter="url(#haloGlow)"
            style={{ transition: 'opacity 0.4s ease' }}
          />

          {/* ── Base ring — dim, full 360° */}
          <circle
            cx={cx} cy={cy} r={R}
            fill="none"
            stroke={isListening ? '#00FFFF' : '#00CFFF'}
            strokeWidth={orbInCorner ? 1.5 : 2}
            opacity={ringOpacity}
            style={{ transition: 'opacity 0.4s ease' }}
          />

          {/* ── Rotating bright arc — speed driven by voiceState */}
          <g style={{ animation: `orbArcSpin ${arcSpinDuration} linear infinite`, transformOrigin: `${cx}px ${cy}px` }}>
            <circle
              cx={cx} cy={cy} r={R}
              fill="none"
              stroke={isListening ? '#00FFFF' : '#00EFFF'}
              strokeWidth={orbInCorner ? 2.5 : (isListening ? 4.5 : 3.5)}
              strokeDasharray={`${arcLen} ${gapLen}`}
              strokeLinecap="round"
              opacity={arcOpacity}
              filter="url(#arcGlow)"
              style={{ transition: 'stroke-width 0.4s ease' }}
            />
          </g>

          {/* ── Counter-rotating faint arc (opposite direction, shorter) */}
          <g style={{ animation: 'orbArcSpinRev 7s linear infinite', transformOrigin: `${cx}px ${cy}px` }}>
            <circle
              cx={cx} cy={cy} r={R}
              fill="none"
              stroke="#00CFFF"
              strokeWidth={orbInCorner ? 1 : 1.5}
              strokeDasharray={`${C * 0.12} ${C * 0.88}`}
              strokeLinecap="round"
              opacity={0.4}
            />
          </g>

          {/* Inner fill intentionally removed — ring floats in pure black space */}

          {/* ── Cardinal tick marks — N / E / S / W */}
          {!orbInCorner && [0, 90, 180, 270].map((deg) => {
            const rad = (deg - 90) * Math.PI / 180
            const inner = R + 4
            const outer = R + 16
            const mx = (inner + outer) / 2
            return (
              <g key={deg}>
                {/* Long tick */}
                <line
                  x1={cx + inner * Math.cos(rad)} y1={cy + inner * Math.sin(rad)}
                  x2={cx + outer * Math.cos(rad)} y2={cy + outer * Math.sin(rad)}
                  stroke="#00CFFF" strokeWidth={2} opacity={0.7}
                />
                {/* Small dot at midpoint */}
                <circle
                  cx={cx + mx * Math.cos(rad)}
                  cy={cy + mx * Math.sin(rad)}
                  r={1.5}
                  fill="#00CFFF" opacity={0.5}
                />
              </g>
            )
          })}

          {/* ── Diagonal short ticks at 45° — smaller */}
          {!orbInCorner && [45, 135, 225, 315].map((deg) => {
            const rad = (deg - 90) * Math.PI / 180
            const inner = R + 4
            const outer = R + 9
            return (
              <line
                key={deg}
                x1={cx + inner * Math.cos(rad)} y1={cy + inner * Math.sin(rad)}
                x2={cx + outer * Math.cos(rad)} y2={cy + outer * Math.sin(rad)}
                stroke="#00CFFF" strokeWidth={1} opacity={0.3}
              />
            )
          })}

          {/* ── Orbiting particle dot */}
          {!orbInCorner && (
            <g style={{ animation: 'orbArcSpin 5s linear infinite reverse', transformOrigin: `${cx}px ${cy}px` }}>
              <circle
                cx={cx + R}
                cy={cy}
                r={2.5}
                fill="#00FFFF"
                opacity={0.9}
                filter="url(#arcGlow)"
              />
            </g>
          )}

          {/* ── Rotating diamond marks — appear during output/speaking (matches reference 8e5f) */}
          {!orbInCorner && (isSpeaking || isListening) && (
            <g style={{
              animation: `orbArcSpin ${isSpeaking ? '4s' : '7s'} linear infinite`,
              transformOrigin: `${cx}px ${cy}px`,
            }}>
              {[45, 135, 225, 315].map((deg) => {
                const rad = (deg - 90) * Math.PI / 180
                const dr = R + 13
                const dx = cx + dr * Math.cos(rad)
                const dy = cy + dr * Math.sin(rad)
                return (
                  <rect
                    key={deg}
                    x={dx - 3.5} y={dy - 3.5}
                    width={7} height={7}
                    fill="rgba(0,207,255,0.12)"
                    stroke="#00CFFF"
                    strokeWidth={1.2}
                    opacity={isSpeaking ? 0.85 : 0.55}
                    transform={`rotate(45, ${dx}, ${dy})`}
                    filter="url(#arcGlow)"
                  />
                )
              })}
            </g>
          )}
        </svg>

        {/* ── Center label */}
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: orbInCorner ? 0 : 2,
          pointerEvents: 'none',
          overflow: 'hidden',
        }}>
          <span style={{
            fontFamily: "'Orbitron', sans-serif",
            fontSize: orbInCorner ? 7 : 13,
            fontWeight: 700,
            color: '#ffffff',
            letterSpacing: '0.08em',
            textShadow: '0 0 14px rgba(0,207,255,0.9), 0 0 28px rgba(0,207,255,0.4)',
            transition: 'font-size 0.6s ease',
            lineHeight: 1,
            whiteSpace: 'nowrap',
          }}>
            VECTOR
          </span>
          {!orbInCorner && (
            <span style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 9,
              color: 'rgba(0,207,255,0.55)',
              letterSpacing: '0.12em',
              marginTop: 2,
            }}>
              {isOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          )}
        </div>
      </div>

      {/* ── Clock + tagline — only in centered (idle) mode */}
      {!orbInCorner && (
        <div style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, calc(-50% + 95px))',
          textAlign: 'center',
          zIndex: 199,
          pointerEvents: 'none',
        }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 30,
            color: '#00CFFF',
            letterSpacing: '0.14em',
            textShadow: '0 0 24px rgba(0,207,255,0.55)',
            lineHeight: 1,
          }}>
            {time}
          </div>
          <div style={{
            fontFamily: "'Orbitron', sans-serif",
            fontSize: 8,
            color: 'rgba(0,207,255,0.28)',
            letterSpacing: '0.22em',
            marginTop: 10,
          }}>
            VIRTUAL ENTITY FOR COGNITIVE TASKS
          </div>
        </div>
      )}

      <style>{`
        @keyframes orbArcSpin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes orbArcSpinRev {
          from { transform: rotate(0deg); }
          to   { transform: rotate(-360deg); }
        }
      `}</style>
    </>
  )
}
