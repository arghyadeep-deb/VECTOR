import { useState, useRef, useEffect } from 'react'
import { useVectorStore } from './store/vectorStore'
import VectorOrb from './components/VectorOrb'
import BootSequence from './components/BootSequence'
import ContentWindowManager from './components/ContentWindow'
import GestureOverlay from './components/GestureOverlay'
import FortressMode from './components/FortressMode'
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
import ReactorGroup from './components/ReactorGroup'
import CoreStatusPanel from './components/CoreStatusPanel'
import CompassPanel from './components/CompassPanel'
import VoiceWaveform from './components/VoiceWaveform'
import FloatingPanelManager from './components/FloatingPanelManager'
import SystemMetricsPanel from './components/SystemMetricsPanel'
import VectorCodePanel from './components/VectorCodePanel'
import DailyInfoPanel from './components/DailyInfoPanel'
import ModelSwitcher from './components/ModelSwitcher'
import NudgeToast from './components/NudgeToast'
import SecurityPanel from './components/SecurityPanel'
import GoalsPanel from './components/GoalsPanel'
import CouncilPanel from './components/CouncilPanel'
import TasksPanel from './components/TasksPanel'
import MemoryPanel from './components/MemoryPanel'
import HealthPanel from './components/HealthPanel'
import TrainingPanel from './components/TrainingPanel'
import LoopPanel from './components/LoopPanel'
import SchedulerPanel from './components/SchedulerPanel'
import InferencePanel from './components/InferencePanel'
import EmailPanel from './components/EmailPanel'
import ChannelsPanel from './components/ChannelsPanel'
import ProvidersPanel from './components/ProvidersPanel'
import ToolsPanel from './components/ToolsPanel'
import NetworkPanel from './components/NetworkPanel'
import AuditPanel from './components/AuditPanel'
import MeteringPanel from './components/MeteringPanel'
import JupyterPanel from './components/JupyterPanel'
import SandboxPanel from './components/SandboxPanel'
import SensingPanel from './components/SensingPanel'
import MediaPanel from './components/MediaPanel'
import MiningPanel from './components/MiningPanel'
import MCPPanel from './components/MCPPanel'
import VideoPanel from './components/VideoPanel'
import ScraperPanel from './components/ScraperPanel'
import SEOPanel from './components/SEOPanel'
import OAuthPanel from './components/OAuthPanel'
import ResearchPanel from './components/ResearchPanel'
import MigrationPanel from './components/MigrationPanel'
import {
  BrainPanel, CityPanel, ControlPanel, FinanceDistrictPanel, DesignPanel,
  AnalyticsPanel, PrivacyPanel, CodingDistrictPanel, QADistrictPanel,
  ProjectsDistrictPanel, LearningPanel, InterviewPanel, LanguagesPanel,
  NewsPanel, PatternsPanel, ReflectionPanel, RelationshipsPanel, SkillsPanel,
  StartupsPanel, KarpathyPanel, OpsPanel, ChiefPanel, CallsPanel,
  AgencyPanel, DocumentationPanel, GovernancePanel,
} from './components/DistrictPanels'
import InfiniteCanvas from './components/InfiniteCanvas'
import type { PanelPlacement } from './components/InfiniteCanvas'

export default function App() {
  const [focusedPanel, setFocusedPanel] = useState<string | null>(null)
  const cameraRef = useRef<{ focusOn: (x: number, y: number, zoom?: number) => void; reset: () => void } | null>(null)
  const mode = useVectorStore((s) => s.mode)
  const setMode = useVectorStore((s) => s.setMode)
  const bootDone = useVectorStore((s) => s.bootDone)
  const processing = useVectorStore((s) => s.processing)
  const voiceState = useVectorStore((s) => s.voiceState)

  // Border glows on INPUT (user speaking/typing), NOT during VECTOR output/speaking
  const borderActive = (processing || voiceState === 'listening') && voiceState !== 'speaking'

  // Terminal auto-hide in JARVIS_MODE
  const [terminalVisible, setTerminalVisible] = useState(false)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showTerminal = () => {
    setTerminalVisible(true)
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    hideTimerRef.current = setTimeout(() => setTerminalVisible(false), 8000)
  }

  // Show terminal on any keydown in JARVIS_MODE
  useEffect(() => {
    if (mode !== 'JARVIS_MODE') return
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'h') {
        setMode('DASHBOARD_MODE')
        return
      }
      showTerminal()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode])

  // Reset terminal when switching mode
  useEffect(() => {
    if (mode === 'DASHBOARD_MODE') setTerminalVisible(false)
  }, [mode])

  // Ctrl+H in dashboard mode to return to orb
  useEffect(() => {
    if (mode !== 'DASHBOARD_MODE') return
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'h') setMode('JARVIS_MODE')
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode])

  // Fist-hold-3s gesture → FORTRESS_MODE (track consecutive fist frames from GestureOverlay)
  const fistStartRef = useRef<number | null>(null)
  // CommandInput calls setMode via voice detection — we wire it in CommandInput

  // Apply/remove data-jarvis on <html> so CSS can suppress bg effects in orb mode
  useEffect(() => {
    document.documentElement.setAttribute('data-jarvis', mode === 'JARVIS_MODE' ? 'true' : 'false')
  }, [mode])

  const panels: PanelPlacement[] = [
    /* Ring 1 (rf=0.80, rX=768, rY=432, 8 panels) */
    { id: 'telemetry', worldX: 768, worldY: 0, component: <TelemetryPanel />, title: 'Telemetry', fixed: true },
    { id: 'systemMetrics', worldX: 543, worldY: 305, component: <SystemMetricsPanel />, title: 'Metrics', fixed: true },
    { id: 'events', worldX: 0, worldY: 432, component: <CompactEventFeed />, title: 'Events' },
    { id: 'compass', worldX: -543, worldY: 305, component: <CompassPanel />, title: 'Compass', fixed: true },
    { id: 'modelSwitcher', worldX: -768, worldY: 0, component: <ModelSwitcher />, title: 'Model' },
    { id: 'coreStatus', worldX: -543, worldY: -305, component: <CoreStatusPanel />, title: 'Core', fixed: true },
    { id: 'dailyInfo', worldX: 0, worldY: -432, component: <DailyInfoPanel />, title: 'Briefing', fixed: true },
    { id: 'vectorCode', worldX: 543, worldY: -305, component: <VectorCodePanel />, title: 'VectorCode' },
    /* Ring 2 (rf=1.25, rX=1200, rY=675, 10 panels) */
    { id: 'health', worldX: 971, worldY: 397, component: <HealthPanel />, title: 'Health', fixed: true },
    { id: 'training', worldX: 371, worldY: 642, component: <TrainingPanel />, title: 'Training' },
    { id: 'goals', worldX: -371, worldY: 642, component: <GoalsPanel />, title: 'Actions' },
    { id: 'security', worldX: -971, worldY: 397, component: <SecurityPanel />, title: 'Security' },
    { id: 'districts', worldX: -1200, worldY: 0, component: <DistrictsPanel />, title: 'Districts' },
    { id: 'council', worldX: -971, worldY: -397, component: <CouncilPanel />, title: 'Council' },
    { id: 'tasks', worldX: -371, worldY: -642, component: <TasksPanel />, title: 'Tasks' },
    { id: 'memory', worldX: 371, worldY: -642, component: <MemoryPanel />, title: 'Memory' },
    { id: 'loop', worldX: 971, worldY: -397, component: <LoopPanel />, title: 'Loop' },
    { id: 'scheduler', worldX: 1200, worldY: 0, component: <SchedulerPanel />, title: 'Scheduler' },
    /* Ring 3 (rf=1.75, rX=1680, rY=945, 10 panels, offset 18°) */
    { id: 'inference', worldX: 1598, worldY: 292, component: <InferencePanel />, title: 'Inference' },
    { id: 'email', worldX: 988, worldY: 765, component: <EmailPanel />, title: 'Email' },
    { id: 'channels', worldX: 0, worldY: 945, component: <ChannelsPanel />, title: 'Channels' },
    { id: 'providers', worldX: -988, worldY: 765, component: <ProvidersPanel />, title: 'Providers' },
    { id: 'tools', worldX: -1598, worldY: 292, component: <ToolsPanel />, title: 'Tools' },
    { id: 'network', worldX: -1598, worldY: -292, component: <NetworkPanel />, title: 'Network' },
    { id: 'audit', worldX: -988, worldY: -765, component: <AuditPanel />, title: 'Audit' },
    { id: 'metering', worldX: 0, worldY: -945, component: <MeteringPanel />, title: 'Metering' },
    { id: 'jupyter', worldX: 988, worldY: -765, component: <JupyterPanel />, title: 'Harness' },
    { id: 'sandbox', worldX: 1598, worldY: -292, component: <SandboxPanel />, title: 'Sandbox' },
    /* Ring 4 (rf=2.35, rX=2256, rY=1269, 10 panels, offset 36°) */
    { id: 'sensing', worldX: 1825, worldY: 746, component: <SensingPanel />, title: 'Sensing' },
    { id: 'media', worldX: 697, worldY: 1207, component: <MediaPanel />, title: 'Media' },
    { id: 'mining', worldX: -697, worldY: 1207, component: <MiningPanel />, title: 'Mining' },
    { id: 'mcp', worldX: -1825, worldY: 746, component: <MCPPanel />, title: 'MCP' },
    { id: 'video', worldX: -2256, worldY: 0, component: <VideoPanel />, title: 'Video' },
    { id: 'scraper', worldX: -1825, worldY: -746, component: <ScraperPanel />, title: 'Scraper' },
    { id: 'seo', worldX: -697, worldY: -1207, component: <SEOPanel />, title: 'SEO' },
    { id: 'oauth', worldX: 697, worldY: -1207, component: <OAuthPanel />, title: 'OAuth' },
    { id: 'research', worldX: 1825, worldY: -746, component: <ResearchPanel />, title: 'Research' },
    { id: 'migration', worldX: 2256, worldY: 0, component: <MigrationPanel />, title: 'Migration' },
    /* Ring 5 (rf=3.30, rX=3300, rY=1856, 13 panels, 27.69° spacing) */
    { id: 'brain', worldX: 3300, worldY: 0, component: <BrainPanel />, title: 'Brain' },
    { id: 'city', worldX: 2926, worldY: 859, component: <CityPanel />, title: 'City' },
    { id: 'control', worldX: 1874, worldY: 1528, component: <ControlPanel />, title: 'Control' },
    { id: 'finance', worldX: 396, worldY: 1843, component: <FinanceDistrictPanel />, title: 'Finance' },
    { id: 'design', worldX: -1169, worldY: 1736, component: <DesignPanel />, title: 'Design' },
    { id: 'analytics', worldX: -2471, worldY: 1230, component: <AnalyticsPanel />, title: 'Analytics' },
    { id: 'privacy', worldX: -3210, worldY: 431, component: <PrivacyPanel />, title: 'Privacy' },
    { id: 'coding_district', worldX: -3210, worldY: -431, component: <CodingDistrictPanel />, title: 'Coding' },
    { id: 'qa_district', worldX: -2471, worldY: -1230, component: <QADistrictPanel />, title: 'QA' },
    { id: 'projects_district', worldX: -1169, worldY: -1736, component: <ProjectsDistrictPanel />, title: 'Projects' },
    { id: 'learning', worldX: 396, worldY: -1843, component: <LearningPanel />, title: 'Learning' },
    { id: 'interview', worldX: 1874, worldY: -1528, component: <InterviewPanel />, title: 'Interview' },
    { id: 'languages', worldX: 2926, worldY: -859, component: <LanguagesPanel />, title: 'Languages' },
    /* Ring 6 (rf=4.20, rX=4200, rY=2363, 13 panels, 13.85° offset) */
    { id: 'news', worldX: 4078, worldY: 565, component: <NewsPanel />, title: 'News' },
    { id: 'patterns', worldX: 3146, worldY: 1565, component: <PatternsPanel />, title: 'Patterns' },
    { id: 'reflection', worldX: 1488, worldY: 2210, component: <ReflectionPanel />, title: 'Reflection' },
    { id: 'relationships', worldX: -504, worldY: 2347, component: <RelationshipsPanel />, title: 'Relationships' },
    { id: 'skills', worldX: -2385, worldY: 1945, component: <SkillsPanel />, title: 'Skills' },
    { id: 'startups', worldX: -3724, worldY: 1094, component: <StartupsPanel />, title: 'Startups' },
    { id: 'karpathy', worldX: -4200, worldY: 0, component: <KarpathyPanel />, title: 'Karpathy' },
    { id: 'ops', worldX: -3724, worldY: -1094, component: <OpsPanel />, title: 'Ops' },
    { id: 'chief', worldX: -2385, worldY: -1945, component: <ChiefPanel />, title: 'Chief' },
    { id: 'calls', worldX: -504, worldY: -2347, component: <CallsPanel />, title: 'Calls' },
    { id: 'agency', worldX: 1488, worldY: -2210, component: <AgencyPanel />, title: 'Agency' },
    { id: 'documentation', worldX: 3146, worldY: -1565, component: <DocumentationPanel />, title: 'Docs' },
    { id: 'governance', worldX: 4078, worldY: -565, component: <GovernancePanel />, title: 'Governance' },
  ]

  return (
    <>
      <BootSequence />
      {mode === 'DASHBOARD_MODE' && <AmbientTheme />}
      <DataPoller />

      {/* Input border — glows on user input only (speaking/typing), not during VECTOR output */}
      <div style={{
        position: 'fixed', inset: 0,
        border: '2px solid #00CFFF',
        pointerEvents: 'none', zIndex: 9002,
        opacity: borderActive ? 1 : 0,
        transition: 'opacity 0.1s ease',
      }} />

      {/* Wake state grid — appears when voice session is active (reference: faint square boxes) */}
      {mode === 'JARVIS_MODE' && bootDone && voiceState !== 'idle' && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1, pointerEvents: 'none',
          backgroundImage: `
            repeating-linear-gradient(0deg, transparent, transparent 59px, rgba(0,207,255,0.035) 59px, rgba(0,207,255,0.035) 60px),
            repeating-linear-gradient(90deg, transparent, transparent 59px, rgba(0,207,255,0.035) 59px, rgba(0,207,255,0.035) 60px)
          `,
          opacity: 1,
          animation: 'fadeInGrid 0.8s ease',
        }} />
      )}

      {/* Permanent subtle edge glow — always on in JARVIS_MODE (matches reference) */}
      {mode === 'JARVIS_MODE' && bootDone && (
        <div style={{
          position: 'fixed', inset: 0,
          border: '1px solid rgba(0,207,255,0.12)',
          boxShadow: 'inset 0 0 40px rgba(0,207,255,0.04)',
          pointerEvents: 'none', zIndex: 9001,
        }} />
      )}

      {/* Minimal mode toggle — barely visible ≡ icon, Ctrl+H shortcut */}
      {bootDone && (
        <div
          onClick={() => setMode(mode === 'JARVIS_MODE' ? 'DASHBOARD_MODE' : 'JARVIS_MODE')}
          title={mode === 'JARVIS_MODE' ? 'Ctrl+H: Switch to HUD' : 'Ctrl+H: Switch to Orb'}
          style={{
            position: 'fixed', top: 8, right: 10, zIndex: 500,
            cursor: 'pointer', opacity: 0.18,
            fontFamily: "'Orbitron', sans-serif", fontSize: 11,
            color: '#00CFFF', padding: '3px 6px',
            transition: 'opacity 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = '0.7')}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.18')}
        >
          ≡
        </div>
      )}

      {/* Star background: full opacity in DASHBOARD_MODE, very faint in JARVIS_MODE */}
      {bootDone && (
        <div style={{ opacity: mode === 'JARVIS_MODE' ? 0.15 : 1, pointerEvents: 'none' }}>
          <BackgroundCanvas />
        </div>
      )}

      {/* Always active after boot — both modes */}
      {bootDone && <GestureOverlay />}
      {bootDone && <ContentWindowManager />}

      {mode === 'JARVIS_MODE' && bootDone && (
        <>
          <div style={{ position: 'fixed', inset: 0, background: '#000', zIndex: -1 }} />
          <VectorOrb />

          {/* Terminal — hidden by default, shown on keypress, auto-hides after 8s */}
          <div style={{
            position: 'fixed', bottom: 0, left: '50%', transform: 'translateX(-50%)',
            width: 'min(860px, calc(100vw - 40px))', zIndex: 100,
            borderTop: '1px solid rgba(0,212,255,0.10)',
            boxShadow: '0 -4px 30px rgba(0,0,0,0.6)',
            opacity: terminalVisible ? 1 : 0,
            pointerEvents: terminalVisible ? 'auto' : 'none',
            transition: 'opacity 0.3s ease',
          }}
          onMouseMove={showTerminal}
          >
            <CommandInput />
          </div>

          {/* Hint when terminal hidden */}
          {!terminalVisible && (
            <div style={{
              position: 'fixed', bottom: 10, left: '50%', transform: 'translateX(-50%)',
              fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
              color: 'rgba(0,207,255,0.18)', letterSpacing: '0.22em',
              pointerEvents: 'none', animation: 'v-pulse 2.5s ease-in-out infinite',
              zIndex: 99,
            }}>
              _ press any key
            </div>
          )}
        </>
      )}

      {/* DASHBOARD MODE — full 64-panel infinite canvas */}
      {mode === 'DASHBOARD_MODE' && (<>

      {/* Reactor always fixed at screen center */}
      <ReactorGroup />

      <InfiniteCanvas
        panels={panels}
        focusedPanel={focusedPanel}
        onFocusPanel={setFocusedPanel}
        cameraRef={cameraRef}
      >
        <VectorScene />
        <Decorations />
      </InfiniteCanvas>

      {/* Fixed overlays on top */}
      <TopBar />
      <QuickActions />
      <VectorOverlay />
      <VoiceWaveform />

      {/* Fixed HUD panels — always visible regardless of scroll/zoom */}
      <div style={{ position: 'fixed', top: 52, left: 10, width: 180, zIndex: 45, cursor: 'pointer' }}
        onClick={() => setFocusedPanel('compass')}>
        <CompassPanel />
      </div>
      <div style={{ position: 'fixed', top: 52, right: 10, width: 180, zIndex: 45, cursor: 'pointer' }}
        onClick={() => setFocusedPanel('telemetry')}>
        <TelemetryPanel />
      </div>
      <div style={{ position: 'fixed', bottom: 50, right: 10, width: 180, zIndex: 45, cursor: 'pointer' }}
        onClick={() => setFocusedPanel('systemMetrics')}>
        <SystemMetricsPanel />
      </div>
      <div style={{ position: 'fixed', bottom: 50, right: 200, width: 180, zIndex: 45, cursor: 'pointer' }}
        onClick={() => setFocusedPanel('coreStatus')}>
        <CoreStatusPanel />
      </div>
      <div style={{ position: 'fixed', bottom: 32, left: 10, width: 180, zIndex: 45, cursor: 'pointer' }}
        onClick={() => setFocusedPanel('dailyInfo')}>
        <DailyInfoPanel />
      </div>
      <div style={{ position: 'fixed', bottom: 50, left: 200, width: 180, zIndex: 45, cursor: 'pointer' }}
        onClick={() => setFocusedPanel('health')}>
        <HealthPanel />
      </div>

      <FloatingPanelManager />
      <NudgeToast />

      {/* Fixed command terminal at bottom — leave side margins for HUD panels */}
      <div style={{
        position: 'fixed', bottom: 0, left: '50%', transform: 'translateX(-50%)',
        width: 'min(960px, calc(100vw - 220px))', zIndex: 100,
        borderTop: '1px solid rgba(0,212,255,0.12)',
        boxShadow: '0 -4px 30px rgba(0,0,0,0.5)',
      }}>
        <CommandInput />
      </div>
      </>)}
    </>
  )
}
