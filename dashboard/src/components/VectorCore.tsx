/**
 * VectorCore — the central JARVIS holographic orb.
 * Animated concentric hexagons with rotating rings and pulse effects.
 */
import { AppStatus } from '../App'

interface Props { status: AppStatus }

const STATUS_COLOR: Record<AppStatus, string> = {
  offline: '#FF3B30', connecting: '#FFB800', online: '#00D4FF',
  thinking: '#1A8FFF', speaking: '#30FF6A',
}

export function VectorCore({ status }: Props) {
  const color = STATUS_COLOR[status]
  const isActive = status !== 'offline'

  return (
    <div style={{ position: 'absolute', width: 160, height: 160 }}>
      <svg width="160" height="160" viewBox="0 0 160 160" style={{ position: 'absolute', inset: 0 }}>
        {/* Outer rotating ring */}
        <g className="spin-slow" style={{ transformOrigin: '80px 80px' }}>
          <circle cx="80" cy="80" r="72" fill="none" stroke={color} strokeWidth="0.5"
            strokeDasharray="8 4" opacity="0.4" />
          <circle cx="80" cy="12" r="3" fill={color} opacity="0.8" />
          <circle cx="80" cy="148" r="3" fill={color} opacity="0.8" />
        </g>

        {/* Inner rotating ring (reverse) */}
        <g className="spin-slow-reverse" style={{ transformOrigin: '80px 80px' }}>
          <circle cx="80" cy="80" r="58" fill="none" stroke={color} strokeWidth="0.5"
            strokeDasharray="4 8" opacity="0.3" />
          <line x1="80" y1="22" x2="80" y2="32" stroke={color} strokeWidth="1" opacity="0.6" />
          <line x1="80" y1="128" x2="80" y2="138" stroke={color} strokeWidth="1" opacity="0.6" />
          <line x1="22" y1="80" x2="32" y2="80" stroke={color} strokeWidth="1" opacity="0.6" />
          <line x1="128" y1="80" x2="138" y2="80" stroke={color} strokeWidth="1" opacity="0.6" />
        </g>

        {/* Outer hexagon */}
        <polygon points="80,26 114,46 114,86 80,106 46,86 46,46"
          fill="none" stroke={color} strokeWidth="1" opacity="0.5" />

        {/* Inner hexagon */}
        <polygon points="80,42 104,56 104,84 80,98 56,84 56,56"
          fill={`${color}08`} stroke={color} strokeWidth="0.8" opacity="0.7" />

        {/* Core hex */}
        <polygon points="80,56 96,65 96,83 80,92 64,83 64,65"
          fill={`${color}15`} stroke={color} strokeWidth="1.2" />

        {/* Pulse ring */}
        {isActive && (
          <circle cx="80" cy="80" r="38" fill="none" stroke={color}
            strokeWidth="1" opacity="0.6" className="pulse-ring" />
        )}

        {/* Center V logo */}
        <text x="80" y="85" textAnchor="middle" fill={color}
          fontSize="22" fontFamily="monospace" fontWeight="bold"
          className={isActive ? 'text-glow' : ''} style={{ textShadow: `0 0 15px ${color}` }}>
          V
        </text>

        {/* Status dots at hex vertices */}
        {[[80,26],[114,46],[114,86],[80,106],[46,86],[46,46]].map(([x,y], i) => (
          <circle key={i} cx={x} cy={y} r="3" fill={color} opacity="0.8"
            className={i % 2 === 0 ? 'status-blink' : ''} />
        ))}

        {/* Scan line */}
        {status === 'thinking' && (
          <line x1="46" y1="65" x2="114" y2="65" stroke={color} strokeWidth="1"
            opacity="0.4" className="data-line" />
        )}

        {/* Cross-hairs */}
        <line x1="80" y1="0" x2="80" y2="20" stroke={color} strokeWidth="0.5" opacity="0.3" />
        <line x1="80" y1="140" x2="80" y2="160" stroke={color} strokeWidth="0.5" opacity="0.3" />
        <line x1="0" y1="80" x2="20" y2="80" stroke={color} strokeWidth="0.5" opacity="0.3" />
        <line x1="140" y1="80" x2="160" y2="80" stroke={color} strokeWidth="0.5" opacity="0.3" />
      </svg>
    </div>
  )
}
