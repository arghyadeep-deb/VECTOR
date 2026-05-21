import { useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { useCityStore } from './useCityStore'
import { useGlobeStore } from './useGlobeStore'
import type { DistrictData } from './useCityStore'

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let attempt = 0

interface CityUpdateEvent {
  type: 'city_update'
  districts: Array<{ name: string; hp: number; color: string; position: [number, number, number]; agents: string[] }>
}

interface GlobeUpdateEvent {
  type: 'globe_update'
  arcs?: Array<{ fromLat: number; fromLng: number; toLat: number; toLng: number; color: string }>
  pulses?: Array<{ lat: number; lng: number; magnitude: number }>
}

interface AgentMovementEvent {
  type: 'agent_movement'
  agentId: string
  agentName: string
  district: string
  status: string
}

interface EventParticleEvent {
  type: 'event_particle'
  from: string
  to: string
  timestamp: number
  eventType: string
}

type VectorEvent = CityUpdateEvent | GlobeUpdateEvent | AgentMovementEvent | EventParticleEvent

function connect(onMsg: (m: unknown) => void): void {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${window.location.host}/ws`
  try {
    ws = new WebSocket(url)
  } catch {
    return scheduleReconnect(onMsg)
  }
  ws.onopen = () => { attempt = 0 }
  ws.onmessage = (e) => {
    try { onMsg(JSON.parse(e.data)) } catch { /* ignore */ }
  }
  ws.onerror = () => { /* close fires */ }
  ws.onclose = () => { ws = null; scheduleReconnect(onMsg) }
}

function scheduleReconnect(onMsg: (m: unknown) => void) {
  const delay = Math.min(30_000, 1000 * 2 ** Math.min(attempt, 5))
  attempt += 1
  if (reconnectTimer) clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(() => connect(onMsg), delay)
}

export function useVectorEvents(): void {
  const addEvent = useVectorStore((s) => s.addEvent)
  const setDistricts = useCityStore((s) => s.setDistricts)
  const updateDistrictHP = useCityStore((s) => s.updateDistrictHP)
  const addFlightArc = useGlobeStore((s) => s.addFlightArc)
  const addPulse = useGlobeStore((s) => s.addPulse)

  useEffect(() => {
    const ref = { addEvent, setDistricts, updateDistrictHP, addFlightArc, addPulse }

    const onMsg = (raw: unknown) => {
      if (!raw || typeof raw !== 'object') return
      const m = raw as Record<string, unknown>

      switch (m.type) {
        case 'city_update': {
          const ev = m as unknown as CityUpdateEvent
          if (ev.districts) {
            const list: DistrictData[] = ev.districts.map((d) => ({
              name: d.name,
              hp: d.hp,
              color: d.color,
              position: d.position,
              agents: d.agents || [],
            }))
            ref.setDistricts(list)
          }
          return
        }
        case 'globe_update': {
          const ev = m as unknown as GlobeUpdateEvent
          if (ev.arcs) {
            ev.arcs.forEach((arc, i) => ref.addFlightArc({
              id: `arc-${Date.now()}-${i}`,
              fromLat: arc.fromLat, fromLng: arc.fromLng,
              toLat: arc.toLat, toLng: arc.toLng,
              color: arc.color || '#00CFFF', progress: 0,
            }))
          }
          if (ev.pulses) {
            ev.pulses.forEach((p, i) => ref.addPulse({
              id: `pulse-${Date.now()}-${i}`,
              lat: p.lat, lng: p.lng,
              magnitude: p.magnitude || 1,
              timestamp: Date.now(),
            }))
          }
          return
        }
        case 'agent_movement': {
          const ev = m as unknown as AgentMovementEvent
          if (ev.district && ev.status) {
            ref.addEvent({
              id: `agent-${ev.agentId}-${Date.now()}`,
              timestamp: new Date().toISOString(),
              event_type: `agent_${ev.status}`,
              content: `${ev.agentName} → ${ev.district} (${ev.status})`,
              source: 'ws_city',
            })
          }
          return
        }
        case 'event_particle': {
          const ev = m as unknown as EventParticleEvent
          ref.addEvent({
            id: `particle-${Date.now()}`,
            timestamp: new Date().toISOString(),
            event_type: `cross_district_${ev.eventType}`,
            content: `${ev.from} → ${ev.to}`,
            source: 'ws_city',
          })
          return
        }
        default:
          return
      }
    }

    connect(onMsg)
    return () => { /* keep open */ }
  }, [addEvent, setDistricts, updateDistrictHP, addFlightArc, addPulse])
}
