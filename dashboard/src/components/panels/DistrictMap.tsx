interface Props { currentDistrict: string }

const DISTRICTS = [
  { id: 'governance', label: 'Governance', icon: '◈', color: '#00D4FF' },
  { id: 'security', label: 'Security', icon: '⬡', color: '#FF3B30' },
  { id: 'coding', label: 'Coding', icon: '⟨⟩', color: '#1A8FFF' },
  { id: 'research', label: 'Research', icon: '◎', color: '#30FF6A' },
  { id: 'communications', label: 'Comms', icon: '◈', color: '#FFB800' },
  { id: 'memory_curator', label: 'Memory', icon: '⬟', color: '#CC44FF' },
  { id: 'intelligence', label: 'Intel', icon: '◉', color: '#00D4FF' },
  { id: 'time_calendar', label: 'Calendar', icon: '◇', color: '#1A8FFF' },
  { id: 'finance', label: 'Finance', icon: '◆', color: '#30FF6A' },
  { id: 'health', label: 'Health', icon: '◎', color: '#FF3B30' },
  { id: 'reflection', label: 'Reflect', icon: '○', color: '#FFB800' },
  { id: 'content', label: 'Content', icon: '▷', color: '#CC44FF' },
]

export function DistrictMap({ currentDistrict }: Props) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
      {DISTRICTS.map(d => {
        const active = d.id === currentDistrict
        return (
          <div key={d.id} style={{
            padding: '6px 4px',
            background: active ? `${d.color}12` : 'transparent',
            border: `1px solid ${active ? d.color : 'var(--jarvis-border)'}`,
            borderRadius: 2,
            display: 'flex', alignItems: 'center', gap: 4,
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}>
            <span style={{ fontSize: '0.8rem', color: d.color }}>{d.icon}</span>
            <span style={{
              fontSize: '0.6rem',
              color: active ? d.color : 'var(--jarvis-text-dim)',
              letterSpacing: '0.05em',
            }}>
              {d.label.toUpperCase()}
            </span>
          </div>
        )
      })}
    </div>
  )
}
