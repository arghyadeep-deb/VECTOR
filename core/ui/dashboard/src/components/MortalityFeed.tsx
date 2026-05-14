import { useMemo, useState } from 'react'
import FloatingPanel from './FloatingPanel'
import { useVectorStore } from '../store/vectorStore'

interface MortalityFeedProps {
  onClose: () => void
  zoneStyle?: React.CSSProperties
}

export default function MortalityFeed({ onClose, zoneStyle }: MortalityFeedProps) {
  const agents = useVectorStore((s) => s.agents)

  const { deceased, dying, reborn, council } = useMemo(() => {
    const dead = agents
      .filter((a) => !a.is_alive || (a.health_points ?? 0) <= 0)
      .map((a) => ({
        name: a.name || a.id,
        hp: a.health_points ?? 0,
        cause: 'Agent terminated — zero HP',
        icon: '💀',
      }))
    const risk = agents
      .filter((a) => a.is_alive && (a.health_points ?? 0) > 0 && (a.health_points ?? 0) < 300)
      .sort((a, b) => (a.health_points ?? 0) - (b.health_points ?? 0))
      .map((a) => ({
        name: a.name || a.id,
        hp: a.health_points ?? 0,
        cause: a.status === 'weakened' ? 'Agent weakened — low HP' : 'Resource exhaustion imminent',
        icon: '⚠',
      }))
    const elite = agents
      .filter((a) => a.is_alive && (a.health_points ?? 0) >= 700)
      .sort((a, b) => (b.health_points ?? 0) - (a.health_points ?? 0))
      .map((a) => ({
        name: a.name || a.id,
        hp: a.health_points ?? 0,
        cause: 'Council member — high HP threshold',
        icon: '✦',
      }))
    return { deceased: dead.slice(0, 10), dying: risk.slice(0, 10), reborn: [] as { name: string; hp: number; cause: string; icon: string }[], council: elite.slice(0, 5) }
  }, [agents])

  return (
    <FloatingPanel
      title="MORTALITY FEED"
      onClose={onClose}
      style={{
        ...zoneStyle,
        width: 300,
        maxHeight: '70vh',
        overflowY: 'auto',
      }}
    >
      <div style={{ padding: '4px 0' }}>
        {council.length > 0 && (<><div style={sHeader}>COUNCIL</div>{council.map((e) => <Card key={e.name} {...e} borderColor="#BF5FFF" hpColor="#BF5FFF" fadeIn />)}</>)}
        {deceased.length > 0 && (<><div style={sHeader}>DECEASED</div>{deceased.map((e) => <Card key={e.name} {...e} borderColor="#4a0000" hpColor="#FF3D3D" />)}</>)}
        {dying.length > 0 && (<><div style={sHeader}>AT RISK</div>{dying.map((e) => <Card key={e.name} {...e} borderColor="#FFB300" hpColor="#FFB300" flash />)}</>)}
        {reborn.length > 0 && (<><div style={sHeader}>REBORN</div>{reborn.map((e) => <Card key={e.name} {...e} borderColor="#00FF88" hpColor="#00FF88" fadeIn />)}</>)}
        {deceased.length === 0 && dying.length === 0 && council.length === 0 && (
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a4466', textAlign: 'center', padding: '20px 0', letterSpacing: '0.15em' }}>
            ALL AGENTS STABLE
          </div>
        )}
      </div>
    </FloatingPanel>
  )
}

const sHeader: React.CSSProperties = { fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a4466', letterSpacing: '0.15em', padding: '6px 12px 3px' }

function Card({ name, hp, cause, icon, borderColor, hpColor, flash, fadeIn }: { name: string; hp: number; cause: string; icon: string; borderColor: string; hpColor: string; flash?: boolean; fadeIn?: boolean }) {
  const [anim] = useState(`hf${Math.random() > 0.5 ? '1' : '2'} 1s ease-in-out infinite`)
  return (
    <div style={{ margin: '3px 8px', padding: '6px 8px', borderLeft: `3px solid ${borderColor}`, background: 'rgba(0,207,255,0.02)', animation: fadeIn ? 'fade-in-up 0.5s ease-out' : 'none' }}>
      <style>{`@keyframes hf1{0%,100%{opacity:1}50%{opacity:0.3}}@keyframes hf2{0%,100%{opacity:1}50%{opacity:0.3}}`}</style>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 9, color: '#7ecfed', letterSpacing: '0.08em' }}>{icon} {name}</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: hpColor, animation: flash ? anim : 'none' }}>{hp} HP</span>
      </div>
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#1a4466' }}>{cause}</div>
    </div>
  )
}
