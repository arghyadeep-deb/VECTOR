import { useEffect } from 'react'
import { useVectorStore } from './store/vectorStore'
import { useVectorWS } from './hooks/useVectorWS'
import BootSequence from './components/BootSequence'
import VectorCore from './components/VectorCore'
import VectorHUD from './components/VectorHUD'
import VectorTopBar from './components/VectorTopBar'
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

  // Keyboard shortcut: F key → FORTRESS_MODE toggle
  const setMode = useVectorStore((s) => s.setMode)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'Escape' && mode === 'FORTRESS_MODE') setMode('ORB_MODE')
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode, setMode])

  if (!bootDone) return <BootSequence />

  return (
    <ErrorBoundary>
      <div style={{
        background: '#000',
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

        {/* Top status bar */}
        <VectorTopBar />

        {/* FORTRESS_MODE — full-screen secret operations overlay */}
        {mode === 'FORTRESS_MODE' && <FortressMode />}

        {/* ORB_MODE — main JARVIS ring interface */}
        {mode !== 'FORTRESS_MODE' && (
          <>
            <VectorHUD side="left" />
            <VectorCore />
            <VectorHUD side="right" />
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
          width: 'min(900px, calc(100vw - 440px))',
          zIndex: 100,
        }}>
          <CommandInput />
        </div>
      </div>
    </ErrorBoundary>
  )
}
