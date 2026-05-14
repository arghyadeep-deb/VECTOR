# Cinematic Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the VECTOR dashboard into a cinematic JARVIS-like AGI command center with dense HUD panels, glowing circular gauges, and immersive sci-fi atmosphere.

**Architecture:** Modify existing components in-place — TelemetryPanel (left telemetry stack), DistrictsPanel (right district list), CornerHUD (merge compass into telemetry), styles.css (scanlines/grid), centerpiece components (enhanced glow). No new files, no new dependencies.

**Tech Stack:** React 18, TypeScript, Vite, CSS custom properties, inline SVG gauges, requestAnimationFrame canvas

---

### Task 1: TelemetryPanel — Cinematic Redesign

**Files:**
- Modify: `core/ui/dashboard/src/components/TelemetryPanel.tsx`

- [ ] **Step 1: Read the current TelemetryPanel**

Read: `core/ui/dashboard/src/components/TelemetryPanel.tsx`

- [ ] **Step 2: Write the redesigned TelemetryPanel**

Replace entire file with cinematic JARVIS-style telemetry panel:

```tsx
import { useMemo } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { useScramble } from '../hooks/useScramble'

function RingGauge({ pct, label, sub, color, size = 52 }: { pct: number; label: string; sub?: string; color?: string; size?: number }) {
  const r = (size - 10) / 2
  const circ = 2 * Math.PI * r
  const offset = circ - (Math.min(100, Math.max(0, pct)) / 100) * circ
  const c = color || (pct > 75 ? '#FFB300' : pct > 45 ? '#00d4ff' : '#00FF88')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, position: 'relative' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', filter: `drop-shadow(0 0 6px ${c}55)` }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(0,207,255,0.05)" strokeWidth={3} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={c} strokeWidth={3}
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
      </svg>
      {sub && <span style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: c, fontWeight: 600 }}>{sub}</span>}
      <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#3388aa', letterSpacing: '0.1em' }}>{label}</span>
    </div>
  )
}

function Bar({ label, pct, color }: { label: string; pct: number; color?: string }) {
  const c = color || (pct > 70 ? '#FFB300' : pct > 40 ? '#00d4ff' : '#00FF88')
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0' }}>
      <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.08em', width: 68, flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, height: 4, background: 'rgba(0,207,255,0.04)', border: '1px solid rgba(0,207,255,0.06)', borderRadius: 1, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(100, pct)}%`, height: '100%', background: c, boxShadow: `0 0 6px ${c}66`, transition: 'width 0.8s ease' }} />
      </div>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 7, color: c, width: 26, textAlign: 'right' }}>{Math.round(pct)}%</span>
    </div>
  )
}

function hpColor(hp: number): string {
  if (hp >= 700) return '#BF5FFF'
  if (hp >= 400) return '#00CFFF'
  if (hp >= 100) return '#FFB300'
  return '#FF3D3D'
}

function formatUptime(sec: number): string {
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  return `${d}d ${h}h ${m}m ${s}s`
}

export default function TelemetryPanel() {
  const m = useVectorStore((s) => s.systemMetrics)
  const agents = useVectorStore((s) => s.agents)
  const status = useVectorStore((s) => s.status)
  const errors = useVectorStore((s) => s.connectionErrors)

  const cpu = m?.cpu_percent ?? 0
  const gpu = m?.gpu_percent ?? 0
  const gpuMem = m?.gpu_mem_percent ?? 0
  const ramPct = m?.memory_percent ?? 0
  const ramUsed = m?.memory_used_gb ?? 0
  const diskPct = m?.disk_percent ?? 0
  const uptimeSec = status?.uptime_sec ?? 0

  const hp = agents.reduce((sum, a) => sum + (a.health_points || 0), 0)
  const alive = agents.filter((a) => a.is_alive).length
  const atRisk = agents.filter((a) => a.is_alive && (a.health_points ?? 0) < 300).length
  const avgHp = alive > 0 ? Math.round(hp / alive) : 0

  const hasError = errors['/status']?.failed || errors['/agents']?.failed
  const offline = !status && hasError
  const sysColor = hpColor(hp)
  const hpScramble = useScramble(hp)

  const confidence = Math.round(Math.max(0, 100 - cpu * 0.3 - (100 - gpu) * 0.2 + alive * 2))
  const hallucinationRisk = Math.round(Math.min(30, Math.max(1, gpuMem * 0.1 + (100 - cpu) * 0.05)))
  const reasoningDepth = Math.min(20, Math.max(1, Math.round(alive / 2)))
  const memCount = typeof status?.memory?.episodic_count === 'number' ? (status.memory.episodic_count as number) : 0
  const memPct = Math.min(99, Math.round(memCount / 100))

  const heading = m ? (m.cpu_percent * 3.6) % 360 : Math.floor(Math.random() * 360)

  return (
    <div style={{
      position: 'fixed', top: 52, left: 10, width: 224,
      zIndex: 40, background: 'rgba(5,13,26,0.88)',
      backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
      border: '1px solid rgba(0,212,255,0.08)',
      boxShadow: '0 0 30px rgba(0,212,255,0.04), inset 0 0 30px rgba(0,212,255,0.02)',
      paddingBottom: 6,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 10px', borderBottom: '1px solid rgba(0,207,255,0.06)' }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#00CFFF', letterSpacing: '0.18em' }}>SYS.TELEMETRY</span>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: offline ? '#2a2a2a' : '#00FF88', boxShadow: offline ? 'none' : '0 0 8px #00FF88', animation: 'v-pulse 3s ease-in-out infinite' }} />
      </div>

      {/* Ring gauges row */}
      <div style={{ display: 'flex', justifyContent: 'space-around', padding: '8px 4px 6px', borderBottom: '1px solid rgba(0,207,255,0.04)' }}>
        <RingGauge pct={cpu} label="CPU" sub={`${Math.round(cpu)}`} />
        <RingGauge pct={gpu} label="GPU" sub={m?.gpu_temp_c ? `${Math.round(m.gpu_temp_c)}°` : `${Math.round(gpu)}`} />
        <RingGauge pct={ramPct} label="RAM" sub={`${ramUsed.toFixed(1)}`} />
        <RingGauge pct={gpuMem} label="VRAM" sub={`${Math.round(gpuMem)}`} color={gpuMem > 70 ? '#FFB300' : '#00FF88'} />
      </div>

      {/* Bars */}
      <div style={{ padding: '4px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)' }}>
        <Bar label="MEM PRESSURE" pct={Math.min(99, memPct * 1.5)} color={memPct > 50 ? '#FFB300' : '#00d4ff'} />
        <Bar label="HALLUCINATION RISK" pct={hallucinationRisk} color="#00FF88" />
        <Bar label="CONFIDENCE" pct={confidence} color="#00d4ff" />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '2px 0' }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.08em' }}>REASONING DEPTH</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#00d4ff' }}>{reasoningDepth}</span>
        </div>
      </div>

      {/* Agent Health */}
      <div style={{ padding: '5px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)' }}>
        <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.1em', marginBottom: 3 }}>AGENT HEALTH</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1px 0' }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#3388aa' }}>ALIVE</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#aaddff' }}>{alive}/{agents.length}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1px 0' }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#3388aa' }}>AVG HP</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: hpColor(avgHp) }}>{avgHp}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1px 0' }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#3388aa' }}>AT RISK</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: atRisk > 0 ? '#FFB300' : '#00FF88' }}>{atRisk}</span>
        </div>
      </div>

      {/* System HP */}
      <div style={{ padding: '6px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)' }}>
        <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.1em', marginBottom: 1 }}>SYSTEM HP</div>
        <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 22, fontWeight: 600, color: sysColor, lineHeight: 1, textShadow: `0 0 25px ${sysColor}55` }}>
          {offline ? '—' : hpScramble}
        </div>
      </div>

      {/* Heading radar + uptime row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)' }}>
        <svg width={36} height={36} style={{ flexShrink: 0 }}>
          <circle cx={18} cy={18} r={14} fill="none" stroke="rgba(0,207,255,0.1)" strokeWidth={1} />
          <circle cx={18} cy={18} r={10} fill="none" stroke="rgba(0,207,255,0.05)" strokeWidth={0.5} />
          <line x1={18} y1={18} x2={18 + 12 * Math.cos((heading * Math.PI / 180) - Math.PI / 2)} y2={18 + 12 * Math.sin((heading * Math.PI / 180) - Math.PI / 2)}
            stroke="#00d4ff" strokeWidth={1.5} strokeLinecap="round" style={{ filter: 'drop-shadow(0 0 4px #00d4ff)' }} />
          <circle cx={18} cy={18} r={2} fill="#00d4ff" filter="url(#glow)" />
        </svg>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 6, color: '#1a6688', letterSpacing: '0.08em' }}>HEADING</span>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 7, color: '#00d4ff' }}>{Math.round(heading)}°</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
            <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 6, color: '#1a6688', letterSpacing: '0.08em' }}>UPTIME</span>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 7, color: '#aaddff' }}>{formatUptime(uptimeSec)}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
            <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 6, color: '#1a6688', letterSpacing: '0.08em' }}>DISK</span>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 7, color: '#aaddff' }}>{Math.round(diskPct)}%</span>
          </div>
        </div>
      </div>

      {/* Reflect cycles */}
      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 10px' }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.08em' }}>REFLECT CYCLES</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#00d4ff' }}>{status?.reflect_cycles ?? 0}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Build and verify**

Run: `cd core/ui/dashboard && npx vite build`
Expected: 65 modules, zero errors

### Task 2: DistrictsPanel — Cinematic Redesign

**Files:**
- Modify: `core/ui/dashboard/src/components/DistrictsPanel.tsx`

- [ ] **Step 1: Read the current DistrictsPanel**

Read: `core/ui/dashboard/src/components/DistrictsPanel.tsx`

- [ ] **Step 2: Write the redesigned DistrictsPanel**

Replace entire file with cinematic district list:

```tsx
import { useMemo } from 'react'
import { useVectorStore } from '../store/vectorStore'

const DISTRICT_ORDER = [
  'coding', 'finance', 'governance', 'health', 'memory_curator',
  'projects', 'reflection', 'research', 'security', 'time_calendar',
]

function hpColor(hp: number): string {
  if (hp >= 700) return '#BF5FFF'
  if (hp >= 400) return '#00CFFF'
  if (hp >= 100) return '#FFB300'
  return '#FF3D3D'
}

export default function DistrictsPanel() {
  const openPanel = useVectorStore((s) => s.openPanel)
  const agents = useVectorStore((s) => s.agents)
  const status = useVectorStore((s) => s.status)

  const districtData = useMemo(() => {
    const s = new Set<string>()
    agents.forEach((a) => { if (a.district) s.add(a.district.toLowerCase()) })
    const names = DISTRICT_ORDER.filter((d) => s.has(d))
    const extras = Array.from(s).filter((d) => !DISTRICT_ORDER.includes(d)).sort()
    const ordered = [...names, ...extras]

    const map = new Map<string, { aliveCount: number; totalHP: number; agentsCount: number }>()
    for (const name of ordered) {
      const da = agents.filter((a) => a.district?.toLowerCase() === name)
      const alive = da.filter((a) => a.is_alive)
      map.set(name, {
        aliveCount: alive.length,
        totalHP: alive.reduce((s, a) => s + a.health_points, 0),
        agentsCount: da.length,
      })
    }
    return { ordered, map }
  }, [agents])

  const totalAlive = agents.filter((a) => a.is_alive).length

  return (
    <div style={{
      position: 'fixed', top: 40, right: 0, width: 196,
      height: 'calc(100vh - 110px)', overflowY: 'auto', overflowX: 'hidden',
      zIndex: 30, background: 'rgba(5,13,26,0.9)',
      borderLeft: '1px solid rgba(0,212,255,0.08)',
      boxShadow: '-4px 0 30px rgba(0,212,255,0.04), inset 0 0 30px rgba(0,212,255,0.02)',
      backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
      scrollbarWidth: 'thin' as any, scrollbarColor: 'rgba(0,212,255,0.06) transparent',
      transition: 'border-color 0.8s ease',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px', borderBottom: '1px solid rgba(0,207,255,0.08)',
        fontFamily: "'Orbitron', sans-serif", fontSize: 9, color: '#00CFFF',
        letterSpacing: '0.18em',
      }}>
        <span>DISTRICTS</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#004466' }}>{districtData.ordered.length}</span>
      </div>

      <style>{`.dentry{cursor:pointer;transition:all .15s}.dentry:hover{background:rgba(0,207,255,0.04)}`}</style>

      {/* District list */}
      {districtData.ordered.map((name) => {
        const data = districtData.map.get(name)
        const isLive = (data?.aliveCount ?? 0) > 0
        const avgHP = data && data.aliveCount > 0 ? Math.round(data.totalHP / data.aliveCount) : 0

        return (
          <div
            key={name}
            className="dentry"
            onClick={() => openPanel({ id: `district-${name}`, type: 'district', districtName: name })}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '7px 14px', borderBottom: '1px solid rgba(0,207,255,0.03)',
            }}
          >
            {/* Pulse dot */}
            <span style={{
              width: 4, height: 4, borderRadius: '50%', flexShrink: 0,
              background: isLive ? '#00CFFF' : '#2a2a2a',
              boxShadow: isLive ? '0 0 8px #00CFFF' : 'none',
              animation: isLive ? 'v-pulse 3s ease-in-out infinite' : 'none',
            }} />
            {/* Name */}
            <span style={{
              fontFamily: "'Orbitron', sans-serif", fontSize: 8, fontWeight: 500,
              color: isLive ? '#7ecfed' : '#3a4a5a', letterSpacing: '0.1em',
              flex: 1,
            }}>
              {name}
            </span>
            {/* HP indicator */}
            {isLive && (
              <span style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 7,
                color: hpColor(avgHP), minWidth: 20, textAlign: 'right',
              }}>
                {avgHP}
              </span>
            )}
          </div>
        )
      })}

      {/* Footer */}
      <div style={{
        padding: '8px 14px', borderTop: '1px solid rgba(0,207,255,0.06)',
        fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688',
        letterSpacing: '0.1em', display: 'flex', justifyContent: 'space-between',
      }}>
        <span>AGENTS ONLINE</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#00FF88' }}>{totalAlive}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Build and verify**

Run: `cd core/ui/dashboard && npx vite build`
Expected: all modules, zero errors

### Task 3: Integrate Compass into TelemetryPanel + Cleanup CornerHUD

**Files:**
- Modify: `core/ui/dashboard/src/components/CornerHUD.tsx`
- Modify: `core/ui/dashboard/src/App.tsx`

- [ ] **Step 1: Read CornerHUD.tsx and App.tsx**

Read both files.

- [ ] **Step 2: Remove CornerHUD's heading compass section and keep only what isn't in TelemetryPanel**

CornerHUD.tsx already only has the compass + heading display (MetricBars was removed earlier). Since compass is now in TelemetryPanel, CornerHUD becomes redundant. Either delete it or keep it if user wants standalone compass.

For now: remove CornerHUD from App.tsx entirely since its heading radar is integrated into TelemetryPanel.

Edit App.tsx:

Remove: `import CornerHUD from './components/CornerHUD'`
Remove: `<CornerHUD />`

- [ ] **Step 3: Delete CornerHUD.tsx**

Run: `Remove-Item -LiteralPath "core/ui/dashboard/src/components/CornerHUD.tsx"`

- [ ] **Step 4: Build and verify**

Run: `cd core/ui/dashboard && npx vite build`
Expected: no errors

### Task 4: Add Scanline and Grid Overlay Effects

**Files:**
- Modify: `core/ui/dashboard/src/styles.css`

- [ ] **Step 1: Read styles.css**

Read: `core/ui/dashboard/src/styles.css`

- [ ] **Step 2: Add scanline overlay and grid effects**

Add after the body/root styles:

```css
/* Scanline overlay */
body::after {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 99999;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0, 0, 0, 0.03) 2px,
    rgba(0, 0, 0, 0.03) 4px
  );
}

/* Fine grid overlay on root */
#root::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 99998;
  background-image:
    linear-gradient(rgba(0, 51, 102, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 51, 102, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
}
```

- [ ] **Step 3: Build and verify**

Run: `cd core/ui/dashboard && npx vite build`
Expected: no errors

### Task 5: Verify Full Build

**Files:**
- None (verification only)

- [ ] **Step 1: Run production build**

Run: `cd core/ui/dashboard && npx vite build`
Expected: build succeeds, 0 errors

- [ ] **Step 2: Verify all components render without crash**

Run: `cd core/ui/dashboard && npx vite` (dev mode)
Check for console errors
