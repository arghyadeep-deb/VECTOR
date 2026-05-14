import { useVectorStore } from '../store/vectorStore'

function headingStr(deg: number): string {
  if (deg < 22.5 || deg >= 337.5) return 'N'
  if (deg < 67.5) return 'NE'
  if (deg < 112.5) return 'E'
  if (deg < 157.5) return 'SE'
  if (deg < 202.5) return 'S'
  if (deg < 247.5) return 'SW'
  if (deg < 292.5) return 'W'
  return 'NW'
}

export default function CompassPanel() {
  const m = useVectorStore((s) => s.systemMetrics)
  const heading = m ? (m.cpu_percent * 3.6) % 360 : Math.floor(Math.random() * 360)
  const headingRad = (heading * Math.PI) / 180
  const cx = 60, cy = 60, r = 50

  const nlx = cx + Math.cos(-Math.PI / 2) * (r - 10)
  const nly = cy + Math.sin(-Math.PI / 2) * (r - 10)
  const elx = cx + Math.cos(0) * (r - 10)
  const ely = cy + Math.sin(0) * (r - 10)
  const slx = cx + Math.cos(Math.PI / 2) * (r - 10)
  const sly = cy + Math.sin(Math.PI / 2) * (r - 10)
  const wlx = cx + Math.cos(Math.PI) * (r - 10)
  const wly = cy + Math.sin(Math.PI) * (r - 10)

  const needleLen = r - 12
  const nx = cx + Math.cos(headingRad - Math.PI / 2) * needleLen
  const ny = cy + Math.sin(headingRad - Math.PI / 2) * needleLen

  return (
    <div style={{
      width: '100%',
      zIndex: 35, background: 'rgba(2, 18, 32, 0.92)',
      border: '1px solid rgba(0,207,255,0.2)',
      boxShadow: '0 0 20px #00CFFF22, inset 0 0 30px #00CFFF08',
      padding: '8px',
    }}>
      <div style={{
        fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#3388aa',
        letterSpacing: '0.12em', textAlign: 'center', marginBottom: 4,
      }}>
        HEADING
      </div>
      <svg width={120} height={120} viewBox="0 0 120 120" style={{ display: 'block', margin: '0 auto', filter: 'drop-shadow(0 0 6px #00d4ff33)' }}>
        {/* Outer rotating ring */}
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(0,207,255,0.12)" strokeWidth={1}>
          <animateTransform attributeName="transform" type="rotate" from={`0 ${cx} ${cy}`} to={`360 ${cx} ${cy}`} dur="12s" repeatCount="indefinite" />
        </circle>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(0,207,255,0.06)" strokeWidth={0.5} strokeDasharray="3 6">
          <animateTransform attributeName="transform" type="rotate" from={`360 ${cx} ${cy}`} to={`0 ${cx} ${cy}`} dur="8s" repeatCount="indefinite" />
        </circle>

        {/* Inner ring */}
        <circle cx={cx} cy={cy} r={r - 8} fill="none" stroke="rgba(0,207,255,0.08)" strokeWidth={0.5} />

        {/* Cardinal labels */}
        <text x={nlx} y={nly} textAnchor="middle" dominantBaseline="central"
          fill="#FF3D3D" fontFamily="'Orbitron', sans-serif" fontSize={7} fontWeight="bold"
          style={{ filter: 'drop-shadow(0 0 4px #FF3D3D66)' }}>N</text>
        <text x={elx} y={ely} textAnchor="middle" dominantBaseline="central"
          fill="rgba(0,207,255,0.4)" fontFamily="'Orbitron', sans-serif" fontSize={6}>E</text>
        <text x={slx} y={sly} textAnchor="middle" dominantBaseline="central"
          fill="rgba(0,207,255,0.4)" fontFamily="'Orbitron', sans-serif" fontSize={6}>S</text>
        <text x={wlx} y={wly} textAnchor="middle" dominantBaseline="central"
          fill="rgba(0,207,255,0.4)" fontFamily="'Orbitron', sans-serif" fontSize={6}>W</text>

        {/* Tick marks */}
        {Array.from({ length: 12 }, (_, i) => {
          const a = (i * 30 * Math.PI) / 180 - Math.PI / 2
          const inner = r - 4
          const outer = i % 3 === 0 ? r - 12 : r - 7
          return (
            <line
              key={i}
              x1={cx + Math.cos(a) * outer}
              y1={cy + Math.sin(a) * outer}
              x2={cx + Math.cos(a) * inner}
              y2={cy + Math.sin(a) * inner}
              stroke={i % 3 === 0 ? 'rgba(0,207,255,0.3)' : 'rgba(0,207,255,0.1)'}
              strokeWidth={i % 3 === 0 ? 1 : 0.5}
            />
          )
        })}

        {/* Heading needle */}
        <line x1={cx} y1={cy} x2={nx} y2={ny}
          stroke="#00d4ff" strokeWidth={2} strokeLinecap="round" opacity={0.9}
          style={{ filter: 'drop-shadow(0 0 6px #00d4ff)' }}>
          <animate attributeName="opacity" values="0.7;1;0.7" dur="2s" repeatCount="indefinite" />
        </line>

        {/* Counter-needle (south) */}
        <line x1={cx} y1={cy} x2={cx - Math.cos(headingRad - Math.PI / 2) * (needleLen * 0.4)} y2={cy - Math.sin(headingRad - Math.PI / 2) * (needleLen * 0.4)}
          stroke="rgba(0,207,255,0.2)" strokeWidth={0.8} strokeLinecap="round" />

        {/* Center dot */}
        <circle cx={cx} cy={cy} r={3} fill="#00d4ff" opacity={0.9}>
          <animate attributeName="r" values="2.5;3.5;2.5" dur="1.5s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.7;1;0.7" dur="1.5s" repeatCount="indefinite" />
        </circle>
      </svg>

      <div style={{
        textAlign: 'center', marginTop: 4,
        fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
        color: '#00d4ff', letterSpacing: '0.05em',
      }}>
        {Math.round(heading)}° <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#3388aa' }}>{headingStr(heading)}</span>
      </div>
    </div>
  )
}
