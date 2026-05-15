import AmbientTheme from './components/AmbientTheme'
import VectorScene from './three/VectorScene'
import BackgroundCanvas from './components/BackgroundCanvas'
import DataPoller from './components/DataPoller'
import TopBar from './components/TopBar'
import TelemetryPanel from './components/TelemetryPanel'
import CompactEventFeed from './components/CompactEventFeed'
import CommandInput from './components/CommandInput'
import DistrictsPanel from './components/DistrictsPanel'
import QuickActions from './components/QuickActions'
import VectorOverlay from './components/VectorOverlay'
import Decorations from './components/Decorations'
import ArcReactor from './components/ArcReactor'
import CentralHologram from './components/CentralHologram'
import DecorativeRing from './components/DecorativeRing'
import NeuralPathways from './components/NeuralPathways'
import CommunicationTraces from './components/CommunicationTraces'
import CoreStatusPanel from './components/CoreStatusPanel'
import CompassPanel from './components/CompassPanel'
import VoiceWaveform from './components/VoiceWaveform'
import FloatingPanelManager from './components/FloatingPanelManager'
import SystemMetricsPanel from './components/SystemMetricsPanel'
import VectorCodePanel from './components/VectorCodePanel'
import DailyInfoPanel from './components/DailyInfoPanel'
import ModelSwitcher from './components/ModelSwitcher'
import { Z } from './lib/zIndex'

export default function App() {
  return (
    <>
      <VectorScene />
      <BackgroundCanvas />
      <ArcReactor />
      <CentralHologram />
      <DecorativeRing />
      <NeuralPathways />
      <CommunicationTraces />
      <Decorations />
      <AmbientTheme />

      <DataPoller />
      <TopBar />

      {/* LEFT: Telemetry + SystemMetrics + VectorCode stacked (top section) */}
      <div style={{ position: 'fixed', left: 12, top: 52, width: 220, zIndex: Z.SIDEBARS, display: 'flex', flexDirection: 'column', gap: 5 }}>
        <div style={{ flex: '0 0 auto' }}><TelemetryPanel /></div>
        <div style={{ flex: '0 0 auto' }}><SystemMetricsPanel /></div>
        <div style={{ flex: '0 0 auto' }}><VectorCodePanel /></div>
      </div>

      {/* EVENT FEED: self-positions at left:239, top:45 */}
      <CompactEventFeed />

      {/* DAILY BRIEF: self-positions at bottom-left */}
      <DailyInfoPanel />

      {/* RIGHT OF CENTER: Compass → panels → CoreStatus, 5px left of Districts */}
      <div style={{ position: 'fixed', right: 201, top: 52, bottom: 12, width: 160, zIndex: 30, display: 'flex', flexDirection: 'column', gap: 5 }}>
        <div style={{ flex: '0 0 auto' }}><CompassPanel /></div>
        <div style={{ flex: '0 0 auto' }}><ModelSwitcher /></div>
        <div style={{ flex: '0 0 auto', marginTop: 'auto' }}><CoreStatusPanel /></div>
      </div>

      {/* RIGHT: Districts (full height) */}
      <DistrictsPanel />

      {/* BOTTOM CENTER: Command terminal */}
      <div style={{
        position: 'fixed', left: '50%', transform: 'translateX(-50%)',
        bottom: 80, width: 520, maxWidth: '90vw',
        zIndex: Z.COMMAND_INPUT, pointerEvents: 'auto',
      }}>
        <CommandInput />
      </div>

      <QuickActions />
      <VectorOverlay />
      <VoiceWaveform />
      <FloatingPanelManager />
    </>
  )
}
