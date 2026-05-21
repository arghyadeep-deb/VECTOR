import { create } from 'zustand'

export interface DistrictData {
  name: string
  hp: number
  color: string
  position: [number, number, number]
  agents: string[]
}

interface CityState {
  districts: Map<string, DistrictData>
  selectedDistrict: string | null
  cityMode: '2d' | '3d'
  setDistricts: (list: DistrictData[]) => void
  selectDistrict: (id: string | null) => void
  updateDistrictHP: (id: string, hp: number) => void
  toggleCityMode: () => void
}

export const useCityStore = create<CityState>((set) => ({
  districts: new Map(),
  selectedDistrict: null,
  cityMode: '3d',

  setDistricts: (list) => {
    const m = new Map<string, DistrictData>()
    list.forEach((d) => m.set(d.name, d))
    set({ districts: m })
  },

  selectDistrict: (id) => set({ selectedDistrict: id }),

  updateDistrictHP: (id, hp) => set((s) => {
    const m = new Map(s.districts)
    const existing = m.get(id)
    if (existing) m.set(id, { ...existing, hp })
    return { districts: m }
  }),

  toggleCityMode: () => set((s) => ({ cityMode: s.cityMode === '2d' ? '3d' : '2d' })),
}))
