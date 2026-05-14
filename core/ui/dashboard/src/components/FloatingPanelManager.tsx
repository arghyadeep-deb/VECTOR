import { useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'
import MortalityFeed from './MortalityFeed'
import DistrictDetail from './DistrictDetail'
import DecisionPanel from './DecisionPanel'

const ZONES = [
  { id: 'A', top: 70, right: 210 },
  { id: 'B', top: 70, right: 520 },
  { id: 'C', bottom: 100, right: 210 },
  { id: 'D', bottom: 100, right: 520 },
] as const

function PanelRenderer({ entry, onClose, zoneStyle }: { entry: any; onClose: () => void; zoneStyle: React.CSSProperties }) {
  switch (entry.type) {
    case 'mortality':
      return <MortalityFeed onClose={onClose} zoneStyle={zoneStyle} />
    case 'district':
      return <DistrictDetail district={entry.districtName!} onClose={onClose} zoneStyle={zoneStyle} />
    case 'decision':
      return <DecisionPanel onClose={onClose} zoneStyle={zoneStyle} />
    default:
      return null
  }
}

export default function FloatingPanelManager() {
  const activePanels = useVectorStore((s) => s.activePanels)
  const closePanel = useVectorStore((s) => s.closePanel)

  const zoneAssignments = useMemo(() => {
    const free = [...ZONES]
    const assigned: Record<string, (typeof ZONES)[number]> = {}

    for (const panel of activePanels) {
      let zone: (typeof ZONES)[number] | undefined

      if (panel.type === 'mortality') {
        const aIdx = free.findIndex((z) => z.id === 'A')
        if (aIdx !== -1) {
          zone = free.splice(aIdx, 1)[0]
        }
      }

      if (!zone) {
        zone = free.shift()
      }

      if (zone) {
        assigned[panel.id] = zone
      }
    }

    return assigned
  }, [activePanels])

  if (activePanels.length === 0) return null

  return createPortal(
    <>
      {activePanels.map((entry) => {
        const zone = zoneAssignments[entry.id]
        const zoneStyle: React.CSSProperties = {
          position: 'fixed' as const,
          zIndex: Z.FLOATING,
          width: 300,
          right: zone?.right ?? 210,
          ...(zone && 'top' in zone ? { top: zone.top } : {}),
          ...(zone && 'bottom' in zone ? { bottom: zone.bottom } : {}),
        }
        return <PanelRenderer key={entry.id} entry={entry} onClose={() => closePanel(entry.id)} zoneStyle={zoneStyle} />
      })}
    </>,
    document.body
  )
}
