import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Z } from '../lib/zIndex'

// WMO code to emoji
function wxIcon(code: number): string {
  if (code === 0) return '☀️'
  if (code <= 2) return '🌤️'
  if (code === 3) return '☁️'
  if (code <= 48) return '🌫️'
  if (code <= 55) return '🌦️'
  if (code <= 65) return '🌧️'
  if (code <= 75) return '❄️'
  if (code <= 82) return '🌦️'
  return '⛈️'
}

type DailyData = {
  date: string; time: string; location: string | null
  weather: { temp_c: number; feels_c: number; humidity_pct: number; wind_kmh: number; description: string; code: number } | null
  sunrise: string | null; sunset: string | null
}

export default function DailyInfoPanel() {
  const [data, setData] = useState<DailyData | null>(null)
  const [loading, setLoading] = useState(true)
  const [minimized, setMinimized] = useState(false)
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const fetch = async () => {
      try {
        const d = await api.daily()
        setData(d)
      } catch { /* silent */ }
      setLoading(false)
    }
    fetch()
    const id = setInterval(fetch, 5 * 60 * 1000) // refresh every 5 min
    return () => clearInterval(id)
  }, [])

  // Live clock
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const w = data?.weather
  const ts = time.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })

  return (
    <div style={{
      position: 'fixed', bottom: 32, left: 10, width: 224, zIndex: Z.METRICS,
      background: 'rgba(5,13,26,0.88)',
      backdropFilter: 'blur(14px)',
      border: '1px solid rgba(0,212,255,0.08)',
      boxShadow: '0 0 30px rgba(0,212,255,0.04)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '5px 10px',
        borderBottom: minimized ? 'none' : '1px solid rgba(0,207,255,0.06)',
        fontFamily: "'Orbitron', sans-serif", fontSize: 9, color: '#1a6688', letterSpacing: '0.15em',
        cursor: 'default',
      }}>
        <span>DAILY BRIEF</span>
        <button onClick={() => setMinimized(!minimized)} style={{
          background: 'transparent', border: '1px solid rgba(0,207,255,0.12)',
          color: '#1a6688', cursor: 'pointer', padding: '1px 5px',
          fontFamily: "'Orbitron', sans-serif", fontSize: 7,
        }}>{minimized ? '□' : '–'}</button>
      </div>

      {!minimized && (
        <div style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 5 }}>

          {/* Date + Time */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
            <div>
              <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.1em' }}>DATE</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: '#aaddff' }}>
                {data?.date ?? '—'}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.1em' }}>LOCAL TIME</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#4FC3F7', textShadow: '0 0 10px rgba(0,212,255,0.4)' }}>
                {ts}
              </div>
            </div>
          </div>

          <div style={{ height: 1, background: 'rgba(0,207,255,0.06)' }} />

          {/* Location */}
          <div>
            <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.1em' }}>LOCATION</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: '#aaddff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {loading ? 'SCANNING...' : (data?.location ?? 'UNKNOWN')}
            </div>
          </div>

          <div style={{ height: 1, background: 'rgba(0,207,255,0.06)' }} />

          {/* Weather */}
          {loading ? (
            <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#1a4466', textAlign: 'center', padding: '4px 0' }}>
              FETCHING WEATHER...
            </div>
          ) : w ? (
            <>
              {/* Temp + icon */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.1em' }}>WEATHER</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, color: '#4FC3F7', lineHeight: 1, textShadow: '0 0 15px rgba(0,212,255,0.4)' }}>
                      {Math.round(w.temp_c)}
                    </span>
                    <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 9, color: '#3388aa' }}>°C</span>
                  </div>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#3388aa' }}>
                    Feels {Math.round(w.feels_c)}°C
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 24, lineHeight: 1 }}>{wxIcon(w.code)}</div>
                  <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#3388aa', marginTop: 2, maxWidth: 70, textAlign: 'center', lineHeight: 1.3 }}>
                    {w.description}
                  </div>
                </div>
              </div>

              {/* Humidity + Wind */}
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.08em' }}>HUMIDITY</div>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>{w.humidity_pct}<span style={{ fontSize: 7, color: '#3388aa' }}>%</span></div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.08em' }}>WIND</div>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>{w.wind_kmh}<span style={{ fontSize: 7, color: '#3388aa' }}>km/h</span></div>
                </div>
              </div>

              {/* Sunrise / Sunset */}
              {(data?.sunrise || data?.sunset) && (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.08em' }}>🌅 RISE</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#42A5F5' }}>{data?.sunrise ?? '—'}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.08em' }}>🌇 SET</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#FF8800' }}>{data?.sunset ?? '—'}</div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#1a4466', textAlign: 'center', padding: '4px 0' }}>
              WEATHER UNAVAILABLE
            </div>
          )}

        </div>
      )}
    </div>
  )
}
