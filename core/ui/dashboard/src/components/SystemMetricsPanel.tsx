import { useState } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

function Bar({ value, max = 100, color }: { value: number; max?: number; color: string }) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div style={{ height: 3, background: 'rgba(0,207,255,0.06)', borderRadius: 1, overflow: 'hidden', flex: 1 }}>
      <div style={{
        width: `${pct}%`, height: '100%',
        background: color,
        boxShadow: `0 0 6px ${color}88`,
        transition: 'width 0.8s ease',
      }} />
    </div>
  )
}

function Row({ label, value, unit, bar, barColor = '#4FC3F7', warn }: {
  label: string; value: string | number; unit?: string
  bar?: number; barColor?: string; warn?: boolean
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '3px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 12, color: '#1a6688', letterSpacing: '0.1em' }}>
          {label}
        </span>
        <span style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
          color: warn ? '#42A5F5' : barColor,
          textShadow: warn ? '0 0 8px #42A5F566' : undefined,
        }}>
          {value}{unit && <span style={{ fontSize: 11, color: '#3388aa', marginLeft: 2 }}>{unit}</span>}
        </span>
      </div>
      {bar !== undefined && (
        <Bar value={bar} color={warn ? '#42A5F5' : barColor} />
      )}
    </div>
  )
}

function TempGauge({ temp }: { temp: number | null }) {
  if (temp === null) return (
    <div style={{ textAlign: 'center', padding: '4px 0' }}>
      <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 11, color: '#1a4466' }}>GPU TEMP N/A</span>
    </div>
  )

  const pct = Math.min(100, ((temp - 30) / 70) * 100) // 30°C = 0%, 100°C = 100%
  const color = temp > 85 ? '#FF3D3D' : temp > 70 ? '#42A5F5' : '#4FC3F7'
  const warn = temp > 70

  // Arc SVG gauge
  const r = 28, cx = 36, cy = 36
  const startAngle = -210 * (Math.PI / 180)
  const endAngle = 30 * (Math.PI / 180)
  const totalArc = endAngle - startAngle
  const fillArc = startAngle + totalArc * (pct / 100)

  const arcPath = (from: number, to: number) => {
    const x1 = cx + r * Math.cos(from), y1 = cy + r * Math.sin(from)
    const x2 = cx + r * Math.cos(to), y2 = cy + r * Math.sin(to)
    const large = (to - from) > Math.PI ? 1 : 0
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '4px 0' }}>
      <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 12, color: '#1a6688', letterSpacing: '0.1em', marginBottom: 2 }}>
        GPU TEMP
      </div>
      <svg width={72} height={50} viewBox="0 0 72 50">
        {/* Background arc */}
        <path d={arcPath(startAngle, endAngle)} fill="none" stroke="rgba(0,207,255,0.08)" strokeWidth={4} strokeLinecap="round" />
        {/* Fill arc */}
        <path d={arcPath(startAngle, fillArc)} fill="none" stroke={color} strokeWidth={4} strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 4px ${color}88)` }} />
        {/* Temp text */}
        <text x={cx} y={cy - 2} textAnchor="middle" dominantBaseline="central"
          fill={color} fontFamily="'JetBrains Mono', monospace" fontSize={11} fontWeight="500">
          {Math.round(temp)}
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle"
          fill="#3388aa" fontFamily="'Orbitron', sans-serif" fontSize={6}>
          °C
        </text>
        {warn && (
          <text x={cx} y={cy + 20} textAnchor="middle"
            fill="#42A5F5" fontFamily="'Orbitron', sans-serif" fontSize={5}>
            HOT
          </text>
        )}
      </svg>
    </div>
  )
}

export default function SystemMetricsPanel() {
  const m = useVectorStore((s) => s.systemMetrics)
  const [minimized, setMinimized] = useState(false)

  const cpu = m?.cpu_percent ?? 0
  const memPct = m?.memory_percent ?? 0
  const memUsed = m?.memory_used_gb ?? 0
  const memTotal = m?.memory_total_gb ?? 32
  const diskPct = m?.disk_percent ?? 0
  const diskUsed = m?.disk_used_gb ?? 0
  const diskTotal = m?.disk_total_gb ?? 1
  const netSent = m?.net_sent_rate_mbs ?? 0
  const netRecv = m?.net_recv_rate_mbs ?? 0
  const gpuPct = m?.gpu_percent ?? null
  const gpuMem = m?.gpu_mem_percent ?? null
  const gpuTemp = m?.gpu_temp_c ?? null

  const cpuWarn = cpu > 80
  const memWarn = memPct > 85
  const diskWarn = diskPct > 90
  const gpuWarn = (gpuPct ?? 0) > 90

  return (
    <div
      style={{
        width: '100%',
        zIndex: Z.METRICS,
        background: 'rgba(5,13,26,0.88)',
        backdropFilter: 'blur(14px)',
        WebkitBackdropFilter: 'blur(14px)',
        border: '1px solid rgba(0,212,255,0.08)',
        boxShadow: '0 0 30px rgba(0,212,255,0.04), inset 0 0 30px rgba(0,212,255,0.02)',
        paddingBottom: 4,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '4px 10px',
          borderBottom: minimized ? 'none' : '1px solid rgba(0,207,255,0.06)',
          fontFamily: "'Orbitron', sans-serif", fontSize: 11,
          color: '#1a6688', letterSpacing: '0.15em',
        }}
      >
        <span>SYS METRICS</span>
        <button
          onClick={() => setMinimized(!minimized)}
          style={{
            background: 'transparent', border: '1px solid rgba(0,207,255,0.12)',
            color: '#1a6688', cursor: 'pointer', padding: '1px 5px',
            fontFamily: "'Orbitron', sans-serif", fontSize: 11,
          }}
        >
          {minimized ? '□' : '–'}
        </button>
      </div>

      {!minimized && (
        <div style={{ padding: '4px 10px', display: 'flex', flexDirection: 'column', gap: 0 }}>

          {/* CPU */}
          <Row label="CPU" value={`${Math.round(cpu)}%`} bar={cpu}
            barColor={cpuWarn ? '#42A5F5' : '#4FC3F7'} warn={cpuWarn} />

          {/* RAM */}
          <Row label="RAM" value={`${memUsed.toFixed(1)}/${memTotal.toFixed(0)}G`}
            bar={memPct} barColor={memWarn ? '#42A5F5' : '#4FC3F7'} warn={memWarn} />

          {/* Disk */}
          <Row label="DISK" value={`${diskUsed.toFixed(0)}/${diskTotal.toFixed(0)}G`}
            bar={diskPct} barColor={diskWarn ? '#FF3D3D' : '#aaddff'} warn={diskWarn} />

          {/* Divider */}
          <div style={{ height: 1, background: 'rgba(0,207,255,0.06)', margin: '3px 0' }} />

          {/* GPU */}
          {gpuPct !== null ? (
            <Row label="GPU" value={`${Math.round(gpuPct)}%`} bar={gpuPct}
              barColor={gpuWarn ? '#FF3D3D' : '#64B5F6'} warn={gpuWarn} />
          ) : (
            <Row label="GPU" value="N/A" barColor="#3388aa" />
          )}

          {/* GPU MEM */}
          {gpuMem !== null && (
            <Row label="VRAM" value={`${Math.round(gpuMem)}%`} bar={gpuMem}
              barColor={(gpuMem > 90) ? '#FF3D3D' : '#64B5F6'} warn={gpuMem > 90} />
          )}

          {/* GPU Temp as simple row */}
          {gpuTemp !== null && (
            <Row label="GPU TEMP" value={`${Math.round(gpuTemp)}°C`}
              barColor={gpuTemp > 85 ? '#FF3D3D' : gpuTemp > 70 ? '#42A5F5' : '#4FC3F7'}
              warn={gpuTemp > 70} />
          )}

          {/* Divider */}
          <div style={{ height: 1, background: 'rgba(0,207,255,0.06)', margin: '2px 0' }} />

          {/* Network */}
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
            <div>
              <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 12, color: '#1a6688', letterSpacing: '0.08em' }}>↑ TX</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#81D4FA' }}>
                {netSent.toFixed(1)} <span style={{ fontSize: 12, color: '#3388aa' }}>MB/s</span>
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 12, color: '#1a6688', letterSpacing: '0.08em' }}>↓ RX</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#81D4FA' }}>
                {netRecv.toFixed(1)} <span style={{ fontSize: 12, color: '#3388aa' }}>MB/s</span>
              </div>
            </div>
          </div>

        </div>
      )}
    </div>
  )
}
