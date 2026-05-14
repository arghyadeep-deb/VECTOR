import AmbientTheme from './components/AmbientTheme'
import BackgroundCanvas from './components/BackgroundCanvas'
import DataPoller from './components/DataPoller'
import TopBar from './components/TopBar'
import TelemetryPanel from './components/TelemetryPanel'
import CompactEventFeed from './components/CompactEventFeed'
import CommandInput from './components/CommandInput'
import DistrictsPanel from './components/DistrictsPanel'
import QuickActions from './components/QuickActions'
import JarvisOverlay from './components/JarvisOverlay'
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
import { Z } from './lib/zIndex'

const GAP = 10
const TOP = 45       // below TopBar (40) + 5px gap
const LEFT_W = 224
const RIGHT_W = 196
const MID_W = 150

export default function App() {
  return (
    <>
      <AmbientTheme />
      <BackgroundCanvas />
      <DataPoller />
      <Decorations />
      <DecorativeRing />
      <ArcReactor />
      <CentralHologram />
      <NeuralPathways />
      <CommunicationTraces />

      <TopBar />

      {/* ── LEFT COLUMN: Telemetry → SystemMetrics ── */}
      <div style={{
        position: 'fixed', top: TOP, left: 10,
        width: LEFT_W, zIndex: 50,
        display: 'flex', flexDirection: 'column', gap: GAP,
        maxHeight: `calc(100vh - ${TOP + 50}px)`,
        overflowY: 'auto', scrollbarWidth: 'none',
      }}>
        <TelemetryPanel />
        <SystemMetricsPanel />
      </div>

      {/* ── RIGHT COLUMN: Districts ── */}
      <DistrictsPanel />

      {/* ── MIDDLE-RIGHT COLUMN: CoreStatus → Compass ── */}
      <div style={{
        position: 'fixed', top: TOP, right: RIGHT_W + GAP,
        width: MID_W, zIndex: 50,
        display: 'flex', flexDirection: 'column', gap: GAP,
      }}>
        <CoreStatusPanel />
        <CompassPanel />
      </div>

      {/* ── BOTTOM-LEFT: Event Feed ── */}
      <CompactEventFeed />

      {/* ── BOTTOM-RIGHT: Daily Brief ── */}
      <DailyInfoPanel />

      <QuickActions />

      {/* ── CENTER: Command Input ── */}
      <div style={{
        position: 'fixed',
        top: TOP,
        left: LEFT_W + 10 + GAP,
        right: RIGHT_W + MID_W + GAP * 2,
        bottom: 52,
        zIndex: Z.EVENT_FEED,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
        padding: '10px 16px',
        pointerEvents: 'auto',
      }}>
        <CommandInput />
      </div>

      <JarvisOverlay />
      <VoiceWaveform />
      <FloatingPanelManager />
    </>
  )
}
