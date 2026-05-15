import { useVectorStore } from '../store/vectorStore'
import { fetchStatus } from '../lib/api'
import { Z } from '../lib/zIndex'

const bar: React.CSSProperties = {
  position: 'fixed', bottom: 0, left: 0, right: 0, height: 32, zIndex: Z.TOP_BAR,
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  borderTop: '1px solid rgba(0,212,255,0.15)',
  filter: 'drop-shadow(0 0 6px rgba(0,212,255,0.1))',
  background: 'rgba(5,13,26,0.92)',
  backdropFilter: 'blur(12px)',
  WebkitBackdropFilter: 'blur(12px)',
  clipPath: 'polygon(12px 0%, 100% 0%, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0% 100%, 0% 12px)',
  padding: '0 16px',
}

const btn: React.CSSProperties = {
  background: 'transparent', border: '1px solid rgba(0,212,255,0.12)',
  color: '#1a6688', fontFamily: "'Orbitron', sans-serif", fontSize: 7,
  padding: '4px 12px', cursor: 'pointer', letterSpacing: '0.14em', transition: 'all 0.2s',
  borderRadius: 12,
}

export default function QuickActions() {
  const openPanel = useVectorStore((s) => s.openPanel)
  const activePanels = useVectorStore((s) => s.activePanels)
  const showMortality = activePanels.some((p) => p.type === 'mortality')

  const actions = [
    ['AI NEWS', async () => { window.open('/ui/search?q=AI+news+today', '_blank') }],
    ['HN TOP', async () => {
      const r = await fetch('/ui/hn')
      const d = await r.json()
      const titles = (d.results || []).slice(0, 5).map((x: any) => x.title)
      useVectorStore.getState().setQuickResult({ title: 'HN TOP 5', lines: titles })
    }],
    ['REFRESH', async () => {
      const s = await fetchStatus('/status')
      useVectorStore.getState().setStatus(s)
    }],
    ['COUNCIL', () => { window.open('/docs', '_blank') }],
    ['GOALS', async () => {
      const r = await fetchStatus('/ui/goals')
      const goals = (r.goals || []).slice(0, 5)
      const lines = goals.map((g: any, i: number) => `${i + 1}. ${typeof g === 'object' ? (g.action || JSON.stringify(g)) : g}`)
      useVectorStore.getState().setQuickResult({ title: 'ACTIVE GOALS', lines })
    }],
    ['MORTALITY', () => openPanel({ id: 'mortality', type: 'mortality' })],
  ]

  const btnStyle = (active = false): React.CSSProperties => ({
    ...btn,
    color: active ? '#4FC3F7' : '#1a6688',
    borderColor: active ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.12)',
    boxShadow: active ? '0 0 12px rgba(0,212,255,0.15)' : 'none',
  })

  return (
    <div style={bar}>
      {actions.map(([label, onClick]) => (
        <button
          key={label as string}
          style={btnStyle(label === 'MORTALITY' && showMortality)}
          onClick={onClick as () => void}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = '#4FC3F7'
            e.currentTarget.style.borderColor = 'rgba(0,212,255,0.4)'
            e.currentTarget.style.boxShadow = '0 0 20px rgba(0,212,255,0.2), 0 0 40px rgba(0,212,255,0.1)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = label === 'MORTALITY' && showMortality ? '#4FC3F7' : '#1a6688'
            e.currentTarget.style.borderColor = 'rgba(0,212,255,0.12)'
            e.currentTarget.style.boxShadow = 'none'
          }}
        >
          {label as string}
        </button>
      ))}
    </div>
  )
}
