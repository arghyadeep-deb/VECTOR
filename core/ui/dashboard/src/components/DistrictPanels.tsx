// All 26 new district panels — one file, thin wrappers around DistrictActionPanel.
import { useState } from 'react'
import { api } from '../lib/api'

const PANEL: React.CSSProperties = {
  width: '100%',
  background: 'rgba(5,13,26,0.88)',
  backdropFilter: 'blur(14px)',
  WebkitBackdropFilter: 'blur(14px)',
  border: '1px solid rgba(0,212,255,0.08)',
  boxShadow: '0 0 30px rgba(0,212,255,0.04), inset 0 0 30px rgba(0,212,255,0.02)',
  paddingBottom: 4,
}

interface Preset { label: string; cmd: string }

function DistrictActionPanel({
  title, subtitle, accentColor = '#00CFFF', presets,
}: {
  title: string
  subtitle: string
  accentColor?: string
  presets: Preset[]
}) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [active, setActive] = useState<string | null>(null)

  const run = async (cmd: string, label: string) => {
    setLoading(true)
    setActive(label)
    setResult(null)
    try {
      const r = await api.command(cmd)
      setResult((r.response ?? 'done').slice(0, 200))
    } catch {
      setResult('error connecting to backend')
    } finally {
      setLoading(false)
    }
  }

  const accent33 = accentColor + '33'
  const accent22 = accentColor + '22'
  const accent88 = accentColor + '88'

  return (
    <div style={PANEL}>
      <div style={{
        fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688',
        letterSpacing: '0.15em', padding: '6px 10px 4px',
        borderBottom: '1px solid rgba(0,207,255,0.06)',
      }}>
        {title}
      </div>

      <div style={{ padding: '2px 10px 4px', borderBottom: '1px solid rgba(0,207,255,0.04)' }}>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 7, color: accent88 }}>
          {subtitle}
        </span>
      </div>

      <div style={{ padding: '4px 10px 2px', display: 'flex', flexWrap: 'wrap', gap: 3 }}>
        {presets.map(p => (
          <button
            key={p.label}
            onClick={() => run(p.cmd, p.label)}
            disabled={loading}
            style={{
              background: loading && active === p.label ? accent22 : 'rgba(0,207,255,0.04)',
              border: `1px solid ${accent33}`,
              color: loading && active === p.label ? accentColor : '#4a8aaa',
              fontFamily: "'Orbitron', sans-serif",
              fontSize: 7,
              letterSpacing: '0.06em',
              padding: '2px 6px',
              cursor: loading ? 'wait' : 'pointer',
              borderRadius: 2,
              transition: 'background 0.15s',
            }}
          >
            {loading && active === p.label ? '...' : p.label}
          </button>
        ))}
      </div>

      {result && (
        <div style={{ padding: '3px 10px 2px', borderTop: '1px solid rgba(0,207,255,0.04)', marginTop: 2 }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 7,
            color: '#6a9abf', lineHeight: 1.5,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {result}
          </div>
        </div>
      )}
    </div>
  )
}

// ── District panels ──────────────────────────────────────────────────────────

export function BrainPanel() {
  return <DistrictActionPanel
    title="BRAIN"
    subtitle="cognition / hypotheses / red-team / epistemic"
    accentColor="#7B68EE"
    presets={[
      { label: 'GOALS', cmd: 'show my current goals by horizon — long mid short' },
      { label: 'HYPOTHESIZE', cmd: 'generate a hypothesis from recent observed patterns' },
      { label: 'RED TEAM', cmd: 'red-team check my current plans for weaknesses and blind spots' },
      { label: 'EPISTEMIC', cmd: 'what does VECTOR know and not know right now — epistemic map' },
    ]}
  />
}

export function CityPanel() {
  return <DistrictActionPanel
    title="CITY"
    subtitle="agent registry / evolution / governor dispatch"
    accentColor="#00E5FF"
    presets={[
      { label: 'DISTRICTS', cmd: 'list all 47 VECTOR districts with agent counts and HP' },
      { label: 'EVOLUTION', cmd: 'show agent generation history and evolutionary progress' },
      { label: 'GOVERNOR', cmd: 'what is the governor currently dispatching across districts?' },
    ]}
  />
}

export function ControlPanel() {
  return <DistrictActionPanel
    title="CONTROL"
    subtitle="PC controller / phone / ADB bridge"
    accentColor="#FF9800"
    presets={[
      { label: 'SCREENSHOT', cmd: 'take a screenshot of the current screen' },
      { label: 'PHONE STATUS', cmd: 'check phone ADB connection status' },
      { label: 'PHONE NOTIFS', cmd: 'read current phone notifications via ADB' },
    ]}
  />
}

export function FinanceDistrictPanel() {
  return <DistrictActionPanel
    title="FINANCE"
    subtitle="budget / expenses / tax calendar / LLM costs"
    accentColor="#4CAF50"
    presets={[
      { label: 'BUDGET', cmd: 'analyze my current budget and recent expenses' },
      { label: 'TAX PLAN', cmd: 'show Indian income tax calendar and filing deadlines' },
      { label: 'LLM COSTS', cmd: 'show LLM API costs and token usage stats' },
    ]}
  />
}

export function DesignPanel() {
  return <DistrictActionPanel
    title="DESIGN"
    subtitle="UI component / UX research / image prompts"
    accentColor="#E91E63"
    presets={[
      { label: 'COMPONENT', cmd: 'generate a UI component specification for the current feature' },
      { label: 'IMAGE PROMPT', cmd: 'generate an optimized AI image generation prompt' },
      { label: 'UX RESEARCH', cmd: 'run UX research analysis on the current VECTOR interface' },
    ]}
  />
}

export function AnalyticsPanel() {
  return <DistrictActionPanel
    title="ANALYTICS"
    subtitle="data pipelines / ETL / reports / benchmarks"
    accentColor="#2196F3"
    presets={[
      { label: 'PIPELINE', cmd: 'check data pipeline health status and ETL runs' },
      { label: 'REPORT', cmd: 'generate analytics report for this week' },
      { label: 'BENCHMARK', cmd: 'run performance benchmarks on VECTOR subsystems' },
    ]}
  />
}

export function PrivacyPanel() {
  return <DistrictActionPanel
    title="PRIVACY"
    subtitle="data flow audit / GDPR / redaction"
    accentColor="#9C27B0"
    presets={[
      { label: 'SCAN', cmd: 'scan data flows for privacy policy violations' },
      { label: 'GDPR CHECK', cmd: 'run GDPR compliance check on current data flows' },
      { label: 'AUDIT FLOW', cmd: 'audit which data leaves the device vs stays local' },
    ]}
  />
}

export function CodingDistrictPanel() {
  return <DistrictActionPanel
    title="CODING"
    subtitle="code review / architect / prototype / db optimize"
    accentColor="#00BCD4"
    presets={[
      { label: 'REVIEW', cmd: 'code review recent changes in the VECTOR codebase' },
      { label: 'ARCHITECT', cmd: 'propose architecture improvements for VECTOR systems' },
      { label: 'PROTOTYPE', cmd: 'rapidly prototype a solution for the current task' },
      { label: 'DB OPTIMIZE', cmd: 'analyze and suggest database query optimizations' },
    ]}
  />
}

export function QADistrictPanel() {
  return <DistrictActionPanel
    title="QA"
    subtitle="tests / accessibility / API testing / reality check"
    accentColor="#FF5722"
    presets={[
      { label: 'WRITE TESTS', cmd: 'write tests for the current VECTOR feature' },
      { label: 'REALITY CHECK', cmd: 'is VECTOR production-ready? run a full reality check' },
      { label: 'ACCESSIBILITY', cmd: 'audit VECTOR dashboard for WCAG accessibility issues' },
      { label: 'API TEST', cmd: 'test all VECTOR API endpoints for correctness' },
    ]}
  />
}

export function ProjectsDistrictPanel() {
  return <DistrictActionPanel
    title="PROJECTS"
    subtitle="planner / progress / deadlines / documentation"
    accentColor="#8BC34A"
    presets={[
      { label: 'PROGRESS', cmd: 'show all active project progress and milestones' },
      { label: 'DEADLINES', cmd: 'list upcoming project and KIIT deadlines' },
      { label: 'DOCS', cmd: 'generate documentation summary for current project' },
    ]}
  />
}

export function LearningPanel() {
  return <DistrictActionPanel
    title="LEARNING"
    subtitle="video ingestor / courses / concept extraction"
    accentColor="#FF9800"
    presets={[
      { label: 'TRACK', cmd: 'what courses and topics am I currently tracking?' },
      { label: 'EXTRACT', cmd: 'extract and summarize key concepts from recent learning' },
      { label: 'QUIZ', cmd: 'generate a quiz on the last topic I studied' },
    ]}
  />
}

export function InterviewPanel() {
  return <DistrictActionPanel
    title="INTERVIEW"
    subtitle="mock interviews / questions / company research"
    accentColor="#607D8B"
    presets={[
      { label: 'START', cmd: 'start a mock technical interview session' },
      { label: 'QUESTION', cmd: 'generate a data structures and algorithms interview question' },
      { label: 'COMPANY', cmd: 'research a company for my upcoming interview preparation' },
    ]}
  />
}

export function LanguagesPanel() {
  return <DistrictActionPanel
    title="LANGUAGES"
    subtitle="Hindi / Bengali / Assamese / Japanese / English"
    accentColor="#FFC107"
    presets={[
      { label: 'HINDI', cmd: 'give me a Hindi vocabulary and grammar exercise for today' },
      { label: 'BENGALI', cmd: 'give me a Bengali grammar exercise' },
      { label: 'JAPANESE', cmd: 'give me a Japanese vocabulary and kanji exercise' },
    ]}
  />
}

export function NewsPanel() {
  return <DistrictActionPanel
    title="NEWS"
    subtitle="AI news / market trends / opportunities"
    accentColor="#00BFA5"
    presets={[
      { label: 'AI BRIEF', cmd: 'fetch the latest AI research and industry news highlights' },
      { label: 'MARKET', cmd: 'show current market trends relevant to my startup ideas' },
      { label: 'OPPS', cmd: 'spot opportunities from today news and tech trends' },
    ]}
  />
}

export function PatternsPanel() {
  return <DistrictActionPanel
    title="PATTERNS"
    subtitle="behavior analysis / habits / insights"
    accentColor="#795548"
    presets={[
      { label: 'DETECT', cmd: 'detect behavioral patterns from my recent activity and schedule' },
      { label: 'HABITS', cmd: 'analyze my habits and suggest three concrete improvements' },
      { label: 'INSIGHTS', cmd: 'give me deep insights about my productivity patterns this week' },
    ]}
  />
}

export function ReflectionPanel() {
  return <DistrictActionPanel
    title="REFLECTION"
    subtitle="daily review / journal entry / growth analysis"
    accentColor="#9E9E9E"
    presets={[
      { label: 'DAILY', cmd: 'run the end-of-day reflection review' },
      { label: 'JOURNAL', cmd: 'write a journal entry based on today activities and learnings' },
      { label: 'GROWTH', cmd: 'analyze my personal growth trajectory this month' },
    ]}
  />
}

export function RelationshipsPanel() {
  return <DistrictActionPanel
    title="RELATIONSHIPS"
    subtitle="contacts / communication style / outreach"
    accentColor="#F48FB1"
    presets={[
      { label: 'CONTACTS', cmd: 'show important contacts and relationship health status' },
      { label: 'COMM STYLE', cmd: 'analyze communication style recommendations for key contacts' },
      { label: 'OUTREACH', cmd: 'suggest a relationship outreach plan for this week' },
    ]}
  />
}

export function SkillsPanel() {
  return <DistrictActionPanel
    title="SKILLS"
    subtitle="skill map / gap analysis / mastery tracking"
    accentColor="#26C6DA"
    presets={[
      { label: 'SKILL MAP', cmd: 'show my current skill map with proficiency levels' },
      { label: 'GAP ANALYSIS', cmd: 'run skill gap analysis against my career goals' },
      { label: 'PRACTICE', cmd: 'suggest targeted practice activities for skill improvement' },
    ]}
  />
}

export function StartupsPanel() {
  return <DistrictActionPanel
    title="STARTUPS"
    subtitle="idea validation / market scan / competitor / revenue"
    accentColor="#FF6F00"
    presets={[
      { label: 'VALIDATE', cmd: 'validate my current startup idea with a market reality check' },
      { label: 'MARKET SCAN', cmd: 'scan HackerNews and Reddit for startup opportunities' },
      { label: 'COMPETITOR', cmd: 'run competitor analysis for my startup project' },
    ]}
  />
}

export function KarpathyPanel() {
  return <DistrictActionPanel
    title="KARPATHY LAB"
    subtitle="30-min sessions / neural training / experiments"
    accentColor="#AB47BC"
    presets={[
      { label: 'SESSION', cmd: 'start a 30-minute Andrej Karpathy learning session' },
      { label: 'IMPROVE', cmd: 'propose improvement to the neural training pipeline based on recent experiments' },
      { label: 'HISTORY', cmd: 'show experiment history and neural training progress this month' },
    ]}
  />
}

export function OpsPanel() {
  return <DistrictActionPanel
    title="OPS"
    subtitle="SRE / incidents / SLO / DevOps"
    accentColor="#F44336"
    presets={[
      { label: 'SLO CHECK', cmd: 'check current VECTOR SLO status and error budget' },
      { label: 'INCIDENT', cmd: 'open a new incident report and start response protocol' },
      { label: 'POST-MORTEM', cmd: 'generate post-mortem document for the last incident' },
    ]}
  />
}

export function ChiefPanel() {
  return <DistrictActionPanel
    title="CHIEF OF STAFF"
    subtitle="morning brief / evening brief / task routing"
    accentColor="#78909C"
    presets={[
      { label: 'MORNING BRIEF', cmd: 'give me the executive morning brief for today' },
      { label: 'EVENING BRIEF', cmd: 'give me the evening accomplishment summary' },
      { label: 'ROUTE TASK', cmd: 'intelligently route and prioritize my highest urgency task' },
    ]}
  />
}

export function CallsPanel() {
  return <DistrictActionPanel
    title="CALLS"
    subtitle="call screening / transcription / contacts"
    accentColor="#26A69A"
    presets={[
      { label: 'SCREEN', cmd: 'screen an incoming call and classify relevance' },
      { label: 'TRANSCRIBE', cmd: 'transcribe and summarize the most recent call recording' },
      { label: 'CONTACTS', cmd: 'show contact list with recent call history' },
    ]}
  />
}

export function AgencyPanel() {
  return <DistrictActionPanel
    title="AGENCY"
    subtitle="content strategy / topics / performance / ROI"
    accentColor="#EC407A"
    presets={[
      { label: 'TRENDS', cmd: 'show current content trends relevant to my personal brand' },
      { label: 'CONTENT PLAN', cmd: 'generate a content calendar plan for this week' },
      { label: 'ROI', cmd: 'analyze ROI of recent content and agency efforts' },
    ]}
  />
}

export function DocumentationPanel() {
  return <DistrictActionPanel
    title="DOCUMENTATION"
    subtitle="API reference / auto-generate / changelog"
    accentColor="#42A5F5"
    presets={[
      { label: 'API DOCS', cmd: 'generate API reference documentation for VECTOR endpoints' },
      { label: 'CHANGELOG', cmd: 'generate changelog from recent git commits' },
      { label: 'WEEKLY SUMMARY', cmd: 'generate weekly development progress summary' },
    ]}
  />
}

export function GovernancePanel() {
  return <DistrictActionPanel
    title="GOVERNANCE"
    subtitle="roadmap / credentials / federation / autopilot"
    accentColor="#5C6BC0"
    presets={[
      { label: 'ROADMAP', cmd: 'show VECTOR 50-day development roadmap and current phase status' },
      { label: 'CREDENTIALS', cmd: 'audit API credential and permission status across districts' },
      { label: 'AUTOPILOT', cmd: 'check VECTOR autopilot governance mode status' },
    ]}
  />
}
