import { useEffect, useState } from 'react'
import { useVectorStore } from './store/vectorStore'
import { useVectorWS } from './hooks/useVectorWS'
import BootSequence from './components/BootSequence'
import VectorCore from './components/VectorCore'
import HUDFrame from './components/HUDFrame'
import FortressMode from './components/FortressMode'
import GestureOverlay from './components/GestureOverlay'
import CommandInput from './components/CommandInput'
import ContentWindowManager from './components/ContentWindow'
import VoiceWaveform from './components/VoiceWaveform'
import DataPoller from './components/DataPoller'
import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  const mode = useVectorStore((s) => s.mode)
  const bootDone = useVectorStore((s) => s.bootDone)
  useVectorWS()

  const setMode = useVectorStore((s) => s.setMode)
  const [showTerminal, setShowTerminal] = useState(false)
  const [focusTrigger, setFocusTrigger] = useState(0)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+Enter — toggle terminal
      if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault()
        setShowTerminal((v) => {
          if (!v) setFocusTrigger((n) => n + 1)
          return !v
        })
        return
      }
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      // Escape — close terminal or exit FORTRESS_MODE
      if (e.key === 'Escape') {
        if (showTerminal) { setShowTerminal(false); return }
        if (mode === 'FORTRESS_MODE') setMode('ORB_MODE')
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode, setMode, showTerminal])

  if (!bootDone) return <BootSequence />

  return (
    <ErrorBoundary>
      <div style={{
        background: '#0a0e1a',
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        position: 'relative',
        fontFamily: "'JetBrains Mono', monospace",
      }}>
        {/* Always-on data polling */}
        <DataPoller />

        {/* Always-on gesture tracking (laptop cam) */}
        <GestureOverlay />

        {/* FORTRESS_MODE — full-screen secret operations overlay */}
        {mode === 'FORTRESS_MODE' && <FortressMode />}

        {/* ORB_MODE — single ring orb interface */}
        {mode !== 'FORTRESS_MODE' && (
          <>
            <HUDFrame />
            <VectorCore />
          </>
        )}

        {/* Content windows (map, text responses) — float over everything */}
        <ContentWindowManager />

        {/* Voice waveform indicator — subtle, near the core */}
        <VoiceWaveform />

        {/* Command terminal — always at bottom, always visible */}
        <div style={{
          position: 'fixed', bottom: 0, left: '50%',
          transform: 'translateX(-50%)',
          width: 'min(700px, calc(100vw - 80px))',
          zIndex: 100,
        }}>
          <CommandInput />
        </div>
      </div>
    </ErrorBoundary>
  )
}
