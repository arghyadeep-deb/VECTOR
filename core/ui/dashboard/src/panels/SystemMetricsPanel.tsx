import { useVectorStore } from '../store/vectorStore'

function Gauge({ label, value, max, color, suffix }: {
  label: string
  value: number
  max: number
  color: string
  suffix?: string
}) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontSize: 9, color: '#8899aa', marginBottom: 3,
      }}>
        <span>{label}</span>
        <span style={{ color }}>{value}{suffix ?? '%'}</span>
      </div>
      <div style={{
        height: 4, background: 'rgba(0,212,255,0.06)',
        borderRadius: 2, overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: color,
          borderRadius: 2,
          transition: 'width 0.4s ease',
          boxShadow: `0 0 6px ${color}`,
        }} />
      </div>
    </div>
  )
}

export default function SystemMetricsPanel() {
  const metrics = useVectorStore((s) => s.systemMetrics)

  return (
    <div style={{ padding: 10 }}>
      <div style={{ fontSize: 9, color: '#1a6688', marginBottom: 10, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
        System Resources
      </div>

      {!metrics ? (
        <div style={{ fontSize: 10, color: '#335566', textAlign: 'center', padding: 12 }}>
          No metrics
        </div>
      ) : (
        <>
          <Gauge label="CPU" value={metrics.cpu_percent} max={100} color="#00CFFF" />
          <Gauge label="RAM" value={metrics.memory_percent} max={100} color="#44FF88" />
          <Gauge label="GPU" value={metrics.gpu_percent ?? 0} max={100} color="#FF4444" />
          <Gauge label="GPU Temp" value={metrics.gpu_temp_c ?? 0} max={100} color="#FF8800" suffix="°C" />
          <Gauge label="GPU Mem" value={metrics.gpu_mem_percent ?? 0} max={100} color="#BB66FF" />
          <Gauge label="Disk" value={metrics.disk_percent} max={100} color="#FFDD44" />

          <div style={{
            marginTop: 12, paddingTop: 8,
            borderTop: '1px solid rgba(0,212,255,0.06)',
            fontSize: 8, color: '#445566',
          }}>
            <div>↑ {metrics.net_sent_rate_mbs.toFixed(1)} MB/s · ↓ {metrics.net_recv_rate_mbs.toFixed(1)} MB/s</div>
            <div style={{ marginTop: 2 }}>
              Up {Math.floor(metrics.uptime_seconds / 3600)}h {Math.floor((metrics.uptime_seconds % 3600) / 60)}m
            </div>
            {metrics.gpu_temp_c && (
              <div style={{ marginTop: 2 }}>
                GPU: {metrics.gpu_temp_c}°C
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
