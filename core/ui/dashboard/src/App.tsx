import { useEffect, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { useVectorStore } from './store/vectorStore'
import { useVectorWS } from './hooks/useVectorWS'
import { useVectorEvents } from './hooks/useVectorEvents'
import { useCityStore } from './hooks/useCityStore'
import BootSequence from './components/BootSequence'
import VectorCore from './components/VectorCore'
import HUDFrame from './components/HUDFrame'
import VectorHUD from './components/VectorHUD'
import FortressMode from './components/FortressMode'
import GestureOverlay from './components/GestureOverlay'
import CommandInput from './components/CommandInput'
import ContentWindowManager from './components/ContentWindow'
import VoiceWaveform from './components/VoiceWaveform'
import DataPoller from './components/DataPoller'
import ErrorBoundary from './components/ErrorBoundary'
import CityEnvironment from './three/CityEnvironment'
import WorldStateGlobe from './three/WorldStateGlobe'
import PanelContainer from './panels/PanelContainer'
import AgentStatusPanel from './panels/AgentStatusPanel'
import EventLogPanel from './panels/EventLogPanel'
import SystemMetricsPanel from './panels/SystemMetricsPanel'
import { Z } from './lib/zIndex'

function CityScene() {
  const cityMode = useCityStore((s) => s.cityMode)

  return (
    <Canvas
      camera={{ position: [0, 12, 14], fov: 50 }}
      gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', zIndex: Z.SCENE }}
    >
      {cityMode === '3d' ? <CityEnvironment /> : <WorldStateGlobe />}
      <OrbitControls enablePan enableZoom autoRotate={false} minDistance={4} maxDistance={30} />
    </Canvas>
  )
}

function DashboardPanels() {
  const [panels, setPanels] = useState<Record<string, boolean>>({
    agents: true, events: true, metrics: true,
  })

  const togglePanel = (id: string) => setPanels((p) => ({ ...p, [id]: !p[id] }))
  const closePanel = (id: string) => setPanels((p) => ({ ...p, [id]: false }))

  return (
    <>
      {panels.agents && (
        <PanelContainer id="agents" title="Agent Status" defaultPos={{ x: 20, y: 60 }} defaultSize={{ w: 280, h: 360 }} onClose={closePanel}>
          <AgentStatusPanel />
        </PanelContainer>
      )}
      {panels.events && (
        <PanelContainer id="events" title="Event Log" defaultPos={{ x: 320, y: 60 }} defaultSize={{ w: 360, h: 300 }} onClose={closePanel}>
          <EventLogPanel />
        </PanelContainer>
      )}
      {panels.metrics && (
        <PanelContainer id="metrics" title="System Metrics" defaultPos={{ x: 700, y: 60 }} defaultSize={{ w: 240, h: 320 }} onClose={closePanel}>
          <SystemMetricsPanel />
        </PanelContainer>
      )}

      <div style={{
        position: 'fixed', bottom: 12, left: '50%', transform: 'translateX(-50%)',
        display: 'flex', gap: 8, zIndex: 1001, fontFamily: "'JetBrains Mono', monospace",
      }}>
        {Object.entries({ agents: 'Agents', events: 'Events', metrics: 'Metrics' }).map(([id, label]) => (
          <button
            key={id}
            onClick={() => togglePanel(id)}
            style={{
              padding: '4px 12px', fontSize: 9, cursor: 'pointer',
              background: panels[id] ? 'rgba(0,212,255,0.12)' : 'rgba(5,13,26,0.88)',
              border: `1px solid ${panels[id] ? 'rgba(0,212,255,0.3)' : 'rgba(0,212,255,0.1)'}`,
              color: panels[id] ? '#00CFFF' : '#557799',
              letterSpacing: '0.1em', textTransform: 'uppercase',
            }}
          >
            {panels[id] ? '▾ ' : '▸ '}{label}
          </button>
        ))}
      </div>
    </>
  )
}

export default function App() {
  const mode = useVectorStore((s) => s.mode)
  const bootDone = useVectorStore((s) => s.bootDone)
  const showCity = useVectorStore((s) => s.showGlobe)
  const setShowCity = useVectorStore((s) => s.setShowGlobe)
  useVectorWS()
  useVectorEvents()

  const isAwake = useVectorStore((s) => s.isAwake)
  const hudVisible = useVectorStore((s) => s.hudVisible)
  const setIsAwake = useVectorStore((s) => s.setIsAwake)
  const setHudVisible = useVectorStore((s) => s.setHudVisible)

  const setMode = useVectorStore((s) => s.setMode)
  const [showTerminal, setShowTerminal] = useState(false)
  const [focusTrigger, setFocusTrigger] = useState(0)

  const toggleCityMode = useCityStore((s) => s.toggleCityMode)

  useEffect(() => {
    document.documentElement.setAttribute('data-orb', (!isAwake).toString())
  }, [isAwake])

  useEffect(() => {
    if (isAwake) return
    const handleWake = () => setIsAwake(true)
    window.addEventListener('pointerdown', handleWake)
    window.addEventListener('keydown', handleWake)
    return () => {
      window.removeEventListener('pointerdown', handleWake)
      window.removeEventListener('keydown', handleWake)
    }
  }, [isAwake, setIsAwake])

  useEffect(() => {
    const handleWakeEvent = () => setIsAwake(true)
    window.addEventListener('vector:wake', handleWakeEvent)
    return () => window.removeEventListener('vector:wake', handleWakeEvent)
  }, [setIsAwake])

  const handleDblClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement
    if (
      target.closest('button') ||
      target.closest('input') ||
      target.closest('textarea') ||
      target.closest('.glass-panel')
    ) {
      return
    }
    setHudVisible(!hudVisible)
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'h') {
        e.preventDefault()
        setHudVisible(!hudVisible)
        return
      }
      if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault()
        setShowTerminal((v) => {
          if (!v) setFocusTrigger((n) => n + 1)
          return !v
        })
        return
      }
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'Escape') {
        if (showTerminal) { setShowTerminal(false); return }
        if (mode === 'FORTRESS_MODE') setMode('ORB_MODE')
        if (showCity) setShowCity(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode, setMode, showTerminal, showCity, setShowCity, hudVisible, setHudVisible])

  if (!bootDone) return <BootSequence />

  return (
    <ErrorBoundary>
      <div
        onDoubleClick={handleDblClick}
        style={{
          background: isAwake ? '#0a0e1a' : '#000000',
          width: '100vw',
          height: '100vh',
          overflow: 'hidden',
          position: 'relative',
          fontFamily: "'JetBrains Mono', monospace",
          transition: 'background 1.5s cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        <div className={`jarvis-grid-background ${isAwake ? 'active' : ''}`} />
        <DataPoller />
        <GestureOverlay />

        {mode === 'FORTRESS_MODE' && <FortressMode />}

        {mode !== 'FORTRESS_MODE' && !showCity && (
          <>
            {isAwake && hudVisible && (
              <>
                <HUDFrame />
                <VectorHUD side="left" />
                <VectorHUD side="right" />
              </>
            )}
            <VectorCore />
          </>
        )}

        {showCity && (
          <>
            <CityScene />
            <DashboardPanels />
          </>
        )}

        {isAwake && <ContentWindowManager />}
        {isAwake && <VoiceWaveform />}

        <div style={{
          position: 'fixed', bottom: 0, left: '50%',
          transform: `translateX(-50%) translateY(${showTerminal ? '0%' : '110%'})`,
          transition: 'transform 0.3s cubic-bezier(0.4,0,0.2,1)',
          width: 'min(700px, calc(100vw - 80px))',
          zIndex: 100,
        }}>
          <CommandInput focusTrigger={focusTrigger} />
        </div>

        {isAwake && (
          <button
            onClick={() => { setShowCity(!showCity); if (showCity) toggleCityMode() }}
            style={{
              position: 'fixed', top: 12, right: 12,
              zIndex: 1001, cursor: 'pointer',
              padding: '6px 14px', fontSize: 10,
              background: showCity ? 'rgba(0,212,255,0.15)' : 'rgba(5,13,26,0.85)',
              border: `1px solid ${showCity ? 'rgba(0,212,255,0.4)' : 'rgba(0,212,255,0.12)'}`,
              color: '#00CFFF',
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}
          >
            {showCity ? '▦ City View' : '◈ Dashboard'}
          </button>
        )}
      </div>
    </ErrorBoundary>
  )
}
