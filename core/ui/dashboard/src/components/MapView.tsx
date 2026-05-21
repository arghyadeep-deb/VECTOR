import { useEffect, useRef, useState } from 'react'

interface LocationData { lat: number; lon: number; city: string; region?: string; country?: string }

export default function MapView() {
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstanceRef = useRef<any>(null)
  const [loc, setLoc] = useState<LocationData>({ lat: 20.3549, lon: 85.8193, city: 'Bhubaneswar', region: 'Odisha', country: 'India' })
  const [scanning, setScanning] = useState(true)
  const [scanY, setScanY] = useState(0)

  // Fetch real location
  useEffect(() => {
    fetch('/location/current')
      .then(r => r.json())
      .then((d: LocationData) => setLoc(d))
      .catch(() => {})
  }, [])

  // Scan animation (top→bottom, 1.2s)
  useEffect(() => {
    let start: number | null = null
    let raf: number
    const animate = (ts: number) => {
      if (!start) start = ts
      const prog = Math.min((ts - start) / 1200, 1)
      setScanY(prog * 100)
      if (prog < 1) raf = requestAnimationFrame(animate)
      else setTimeout(() => setScanning(false), 200)
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [])

  // Init map after scan completes
  useEffect(() => {
    if (scanning || !mapRef.current || mapInstanceRef.current) return

    const loadLeaflet = () => {
      // Load CSS
      if (!document.querySelector('#leaflet-css')) {
        const link = document.createElement('link')
        link.id = 'leaflet-css'
        link.rel = 'stylesheet'
        link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
        document.head.appendChild(link)
      }

      const init = () => {
        const L = (window as any).L
        if (!L || !mapRef.current) return

        const map = L.map(mapRef.current, {
          center: [20, 0],   // Start at world view
          zoom: 2,
          zoomControl: false,
          attributionControl: false,
        })
        mapInstanceRef.current = map

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(map)

        // Custom cyan pulsing marker
        const icon = L.divIcon({
          html: `
            <div style="
              width:12px;height:12px;border-radius:50%;
              background:#00CFFF;
              box-shadow:0 0 16px #00CFFF, 0 0 32px rgba(0,207,255,0.6);
              animation:markerPulse 2s ease-in-out infinite;
              position:relative;
            ">
              <div style="
                position:absolute;top:-6px;left:-6px;
                width:24px;height:24px;border-radius:50%;
                border:1.5px solid rgba(0,207,255,0.5);
                animation:markerRing 2s ease-in-out infinite;
              "></div>
            </div>
          `,
          className: '',
          iconSize: [12, 12],
          iconAnchor: [6, 6],
        })

        // Fly from world → user location
        setTimeout(() => {
          map.flyTo([loc.lat, loc.lon], 13, { duration: 2.5, easeLinearity: 0.2 })
          L.marker([loc.lat, loc.lon], { icon }).addTo(map)
        }, 600)
      }

      if ((window as any).L) {
        init()
      } else {
        const script = document.createElement('script')
        script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
        script.onload = init
        document.head.appendChild(script)
      }
    }

    loadLeaflet()
  }, [scanning, loc])

  // Update map if location changes
  useEffect(() => {
    const map = mapInstanceRef.current
    if (map && !scanning) {
      map.flyTo([loc.lat, loc.lon], 13, { duration: 2.0 })
    }
  }, [loc])

  // Listen for voice "show me <place>" events: useVectorWS dispatches
  // 'vector:show-location' with a {query} payload. We hit /sb/geocode
  // (proxied to shadowbroker_server's Nominatim cache) and flyTo the result.
  useEffect(() => {
    const onShow = async (e: Event) => {
      const detail = (e as CustomEvent<{ query?: string }>).detail || {}
      const query = (detail.query || '').trim()
      if (!query) return
      try {
        const r = await fetch(`/sb/geocode?q=${encodeURIComponent(query)}&limit=1`)
        if (!r.ok) return
        const data = await r.json()
        // SB returns either {results:[{lat, lng | lon}]} or [{lat, lng}]
        const first = Array.isArray(data) ? data[0] :
                      Array.isArray(data?.results) ? data.results[0] : data
        if (!first) return
        const lat = Number(first.lat ?? first.latitude)
        const lng = Number(first.lng ?? first.lon ?? first.longitude)
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return
        setLoc({
          lat, lon: lng,
          city: first.label || first.display_name || query,
          region: first.region || '',
          country: first.country || '',
        })
        const map = mapInstanceRef.current
        if (map) map.flyTo([lat, lng], 12, { duration: 2.4 })
      } catch { /* network blip — ignore */ }
    }
    window.addEventListener('vector:show-location', onShow)
    return () => window.removeEventListener('vector:show-location', onShow)
  }, [])

  return (
    <div style={{ width: '100%', position: 'relative' }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '4px 0 8px',
        fontFamily: "'Orbitron', sans-serif", fontSize: 9,
        color: 'rgba(0,207,255,0.6)', letterSpacing: '0.16em',
      }}>
        <span>VECTOR · LOCATION LOCK</span>
        <span style={{ color: scanning ? '#FFAA00' : '#00FF88' }}>
          {scanning ? 'SCANNING...' : `${loc.lat.toFixed(4)}°N · ${loc.lon.toFixed(4)}°E`}
        </span>
      </div>

      {/* Map container */}
      <div style={{ position: 'relative', lineHeight: 0 }}>
        {/* Scan animation overlay */}
        {scanning && (
          <>
            <div style={{
              position: 'absolute', inset: 0, background: '#000',
              zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <span style={{
                fontFamily: "'Orbitron', sans-serif", fontSize: 11,
                color: '#00CFFF', letterSpacing: '0.25em',
                animation: 'v-pulse 0.8s ease-in-out infinite',
              }}>
                SCANNING GLOBAL NETWORK...
              </span>
            </div>
            <div style={{
              position: 'absolute', left: 0, right: 0, top: `${scanY}%`,
              height: 2,
              background: 'linear-gradient(90deg, transparent, #00CFFF, transparent)',
              boxShadow: '0 0 16px #00CFFF',
              zIndex: 11, pointerEvents: 'none',
            }} />
          </>
        )}

        <div ref={mapRef} style={{
          width: '100%', height: 340,
          border: '1px solid rgba(0,207,255,0.12)',
          filter: scanning ? 'brightness(0)' : 'hue-rotate(175deg) saturate(0.6) brightness(0.85)',
          transition: 'filter 0.5s ease',
        }} />

        {/* Crosshair overlay */}
        {!scanning && (
          <div style={{
            position: 'absolute', inset: 0, pointerEvents: 'none',
            border: '1px solid rgba(0,207,255,0.06)',
          }}>
            <div style={{ position: 'absolute', top: '50%', left: 0, right: 0, height: 1, background: 'rgba(0,207,255,0.06)' }} />
            <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'rgba(0,207,255,0.06)' }} />
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', marginTop: 6,
        fontFamily: "'JetBrains Mono', monospace", fontSize: 8,
        color: 'rgba(0,207,255,0.45)', letterSpacing: '0.08em',
      }}>
        <span>{loc.city?.toUpperCase()}{loc.region ? `, ${loc.region}` : ''}</span>
        <span>{loc.country?.toUpperCase() ?? 'INDIA'} · SIGNAL LOCKED</span>
      </div>

      <style>{`
        @keyframes markerPulse {
          0%, 100% { box-shadow: 0 0 16px #00CFFF, 0 0 32px rgba(0,207,255,0.6); }
          50% { box-shadow: 0 0 24px #00CFFF, 0 0 48px rgba(0,207,255,0.8); }
        }
        @keyframes markerRing {
          0%, 100% { transform: scale(1); opacity: 0.8; }
          50% { transform: scale(2.2); opacity: 0; }
        }
        .leaflet-popup-content-wrapper {
          background: rgba(2,10,20,0.95) !important;
          border: 1px solid rgba(0,207,255,0.3) !important;
          border-radius: 2px !important;
        }
        .leaflet-popup-tip { background: rgba(2,10,20,0.95) !important; }
      `}</style>
    </div>
  )
}
