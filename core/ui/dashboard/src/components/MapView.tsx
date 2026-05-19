import { useEffect, useRef, useState } from 'react'

interface LocationData { lat: number; lon: number; city: string }

export default function MapView() {
  const mapRef = useRef<HTMLDivElement>(null)
  const initialized = useRef(false)
  const [loc, setLoc] = useState<LocationData>({ lat: 20.3549, lon: 85.8193, city: 'Bhubaneswar' })

  useEffect(() => {
    fetch('/location/current')
      .then(r => r.json())
      .then((d: LocationData) => setLoc(d))
      .catch(() => {})
  }, [])

  const { lat, lon, city } = loc

  useEffect(() => {
    if (initialized.current || !mapRef.current) return
    initialized.current = true

    // Load Leaflet CSS
    if (!document.querySelector('#leaflet-css')) {
      const link = document.createElement('link')
      link.id = 'leaflet-css'
      link.rel = 'stylesheet'
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
      document.head.appendChild(link)
    }

    // Load Leaflet JS and initialize map
    const initMap = () => {
      const L = (window as any).L
      if (!L || !mapRef.current) return

      const map = L.map(mapRef.current, {
        center: [lat, lon],
        zoom: 15,
        zoomControl: false,
        attributionControl: false,
      })

      // Dark map tiles
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
      }).addTo(map)

      // Custom cyan marker
      const icon = L.divIcon({
        html: `
          <div style="
            width:16px;height:16px;border-radius:50%;
            background:#00CFFF;
            box-shadow:0 0 20px #00CFFF, 0 0 40px rgba(0,207,255,0.6);
            animation:markerPulse 2s ease-in-out infinite;
          "></div>
          <div style="
            position:absolute;top:-4px;left:-4px;
            width:24px;height:24px;border-radius:50%;
            border:2px solid rgba(0,207,255,0.4);
            animation:markerRing 2s ease-in-out infinite;
          "></div>
        `,
        className: '',
        iconSize: [16, 16],
        iconAnchor: [8, 8],
      })

      L.marker([lat, lon], { icon }).addTo(map)
        .bindPopup(`<span style="font-family:Orbitron,sans-serif;font-size:10px;color:#00CFFF">${city.toUpperCase()}</span>`)
        .openPopup()
    }

    if ((window as any).L) {
      initMap()
    } else {
      const script = document.createElement('script')
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
      script.onload = initMap
      document.head.appendChild(script)
    }
  }, [lat, lon, city])

  return (
    <div style={{ width: '100%' }}>
      <div style={{
        fontFamily: "'Orbitron', sans-serif",
        fontSize: 9,
        color: 'rgba(0,207,255,0.5)',
        letterSpacing: '0.15em',
        marginBottom: 6,
        display: 'flex',
        justifyContent: 'space-between',
      }}>
        <span>VECTOR · LOCATION LOCK</span>
        <span style={{ color: '#00FF88' }}>{lat.toFixed(4)}N · {lon.toFixed(4)}E</span>
      </div>

      <div ref={mapRef} style={{
        width: '100%',
        height: 280,
        border: '1px solid rgba(0,207,255,0.15)',
        filter: 'hue-rotate(180deg) saturate(0.7) brightness(0.8)',
      }} />

      <div style={{
        marginTop: 6,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 9,
        color: 'rgba(0,207,255,0.5)',
        display: 'flex',
        justifyContent: 'space-between',
      }}>
        <span>{city.toUpperCase()}</span>
        <span>SIGNAL LOCKED</span>
      </div>

      <style>{`
        @keyframes markerPulse {
          0%, 100% { box-shadow: 0 0 20px #00CFFF, 0 0 40px rgba(0,207,255,0.6); }
          50% { box-shadow: 0 0 30px #00CFFF, 0 0 60px rgba(0,207,255,0.8); }
        }
        @keyframes markerRing {
          0%, 100% { transform: scale(1); opacity: 0.8; }
          50% { transform: scale(1.5); opacity: 0; }
        }
        .leaflet-popup-content-wrapper {
          background: rgba(2,10,20,0.95) !important;
          border: 1px solid rgba(0,207,255,0.3) !important;
          border-radius: 2px !important;
          box-shadow: 0 0 20px rgba(0,207,255,0.2) !important;
        }
        .leaflet-popup-tip { background: rgba(2,10,20,0.95) !important; }
      `}</style>
    </div>
  )
}
