/**
 * VectorMascot — VECTOR's JARVIS-style animated mascot.
 *
 * NOT a human avatar. VECTOR is represented as a geometric AI entity:
 * - A floating hexagonal energy core
 * - Data particle trails
 * - Waveform bars when speaking
 * - Idle breathing animation
 *
 * Aesthetic: Iron Man JARVIS holographic blue — Arghyadeep's VECTOR.
 */
import { AppStatus } from '../App'

interface Props { status: AppStatus }

const STATUS_COLOR: Record<AppStatus, string> = {
  offline: '#FF3B30', connecting: '#FFB800', online: '#00D4FF',
  thinking: '#1A8FFF', speaking: '#30FF6A',
}

const STATUS_LABEL: Record<AppStatus, string> = {
  offline: 'OFFLINE', connecting: 'INITIALIZING', online: 'STANDBY',
  thinking: 'PROCESSING', speaking: 'RESPONDING',
}

export function VectorMascot({ status }: Props) {
  const color = STATUS_COLOR[status]
  const label = STATUS_LABEL[status]

  return (
    <div style={{
      position: 'absolute',
      bottom: -20,
      right: 16,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 4,
    }}>
      {/* Waveform — shown when speaking */}
      {status === 'speaking' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, height: 32, marginBottom: 4 }}>
          {[0.3, 0.6, 1.0, 0.8, 0.5, 0.9, 0.4, 0.7, 1.0, 0.6, 0.3].map((h, i) => (
            <div key={i} className="wave-bar" style={{
              width: 3,
              height: `${h * 100}%`,
              background: color,
              borderRadius: 2,
              animationDelay: `${i * 0.07}s`,
              boxShadow: `0 0 4px ${color}`,
            }} />
          ))}
        </div>
      )}

      {/* Thinking particles */}
      {status === 'thinking' && (
        <div style={{ position: 'relative', width: 60, height: 30 }}>
          {[0, 1, 2, 3, 4].map(i => (
            <div key={i} className="data-line" style={{
              position: 'absolute',
              left: `${i * 20}%`,
              top: `${Math.sin(i) * 30 + 30}%`,
              width: 4, height: 4,
              borderRadius: '50%',
              background: color,
              boxShadow: `0 0 6px ${color}`,
              animationDelay: `${i * 0.4}s`,
            }} />
          ))}
        </div>
      )}

      {/* Mascot mini-hex */}
      <svg width="48" height="48" viewBox="0 0 48 48">
        <g className={status !== 'offline' ? 'pulse-ring' : ''}>
          <polygon points="24,4 42,14 42,34 24,44 6,34 6,14"
            fill={`${color}12`} stroke={color} strokeWidth="1.5" />
          <polygon points="24,12 36,19 36,33 24,40 12,33 12,19"
            fill={`${color}08`} stroke={color} strokeWidth="0.8" opacity="0.6" />
        </g>
        {/* Eye-like center */}
        <ellipse cx="24" cy="24" rx="6" ry="4" fill={color} opacity="0.9"
          style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
        <ellipse cx="24" cy="24" rx="2" ry="2" fill="var(--jarvis-bg)" />
        {/* Scan lines */}
        <line x1="6" y1="24" x2="18" y2="24" stroke={color} strokeWidth="0.5" opacity="0.4" />
        <line x1="30" y1="24" x2="42" y2="24" stroke={color} strokeWidth="0.5" opacity="0.4" />
      </svg>

      {/* Status label */}
      <span style={{
        fontSize: '0.55rem',
        letterSpacing: '0.15em',
        color,
        textShadow: `0 0 8px ${color}`,
        fontFamily: 'monospace',
      }}>
        {label}
      </span>
    </div>
  )
}
