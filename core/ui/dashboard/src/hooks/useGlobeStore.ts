import { create } from 'zustand'

export interface FlightArcData {
  id: string
  fromLat: number
  fromLng: number
  toLat: number
  toLng: number
  color: string
  progress: number
}

export interface VesselMarker {
  id: string
  lat: number
  lng: number
  label: string
  type: string
}

export interface EarthquakePulseData {
  id: string
  lat: number
  lng: number
  magnitude: number
  timestamp: number
}

interface GlobeState {
  flightArcs: FlightArcData[]
  vesselMarkers: VesselMarker[]
  earthquakePulses: EarthquakePulseData[]
  conflictZones: Array<{ lat: number; lng: number; radius: number; intensity: number }>
  addFlightArc: (arc: FlightArcData) => void
  addMarker: (marker: VesselMarker) => void
  addPulse: (pulse: EarthquakePulseData) => void
  clearAll: () => void
}

export const useGlobeStore = create<GlobeState>((set) => ({
  flightArcs: [],
  vesselMarkers: [],
  earthquakePulses: [],
  conflictZones: [],

  addFlightArc: (arc) => set((s) => ({
    flightArcs: [...s.flightArcs, arc].slice(-20),
  })),

  addMarker: (marker) => set((s) => ({
    vesselMarkers: [...s.vesselMarkers, marker].slice(-50),
  })),

  addPulse: (pulse) => set((s) => ({
    earthquakePulses: [...s.earthquakePulses, pulse].slice(-10),
  })),

  clearAll: () => set({
    flightArcs: [],
    vesselMarkers: [],
    earthquakePulses: [],
    conflictZones: [],
  }),
}))
