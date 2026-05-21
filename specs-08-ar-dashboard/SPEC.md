# SPEC-08: AR Dashboard & 3D City Visualization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform VECTOR's dashboard from 15/100 to 80/100 — a Three.js-powered 3D "city" visualization with real-time agent activity animation, a WorldStateGlobe for global intelligence, WebXR AR mode for phone-based spatial overlay, spatial audio cues, and a fully modular dashboard architecture.

**Architecture:** VECTOR's city becomes a literal 3D city in the browser. Districts render as buildings (height = HP/task load), agents as moving dots with activity trails, events as particle streams. A WebXR AR mode overlays this city on the real world via phone camera. Spatial audio places each district's voice in 3D space. A modular dashboard refactor makes all panels pluggable and embeddable in the 3D scene.

**Tech Stack:** Three.js (3D rendering), WebXR API (AR mode), WebAudio API (spatial audio), React + Vite + TypeScript (existing dashboard), zustand (state management), @react-three/fiber (R3F), @react-three/xr (WebXR), d3-geo (globe rendering)

**Score:** Current 15/100 → Target 80/100

---

## 1. Problem Statement

### 1.1 Current Limitations

AR/UI scores 15/100 across five dimensions:

| Dimension | Score | Issue |
|-----------|-------|-------|
| Visualization | 20/100 | Flat React dashboard with text/tables. No 3D, no spatial data representation. Agent status is a text list, not a visual layout. |
| Real-time Feedback | 10/100 | Dashboard polls via WebSocket but shows static data. Agent movement, event flows, and HP changes are not animated. |
| World State | 10/100 | Shadowbroker intel exists (flights, vessels, earthquakes) but rendered as JSON/text. No globe visualization. |
| AR/Phone | 0/100 | No AR, no phone overlay, no spatial interface. Dashboard only works on Legion laptop screen. |
| Audio | 5/100 | Dashboard has no audio output. Voice comes from laptop speakers regardless of which district is active. |

### 1.2 Impact on User Experience

- Dashboard feels like a monitoring tool, not a "virtual city." Users see numbers, not an ecosystem.
- No sense of spatial awareness — user cannot tell which district is active without reading text.
- Shadowbroker intel (real-time flights, conflicts, earthquakes) is text-only — loses the visceral impact of a live globe.
- Phone experience is a scaled-down web page, not an AR overlay.
- No audio cues — user must constantly look at the screen to know what's happening.

### 1.3 Visualization Opportunity

```
CURRENT                             TARGET
┌──────────────────┐               ┌──────────────────────────────────┐
│ VECTOR Dashboard  │               │ 🏙  VECTOR City (3D)            │
│                   │               │                                  │
│  {voice: active}  │               │  ┌──┐ ┌───┐ ┌──┐ ┌────┐         │
│  {research: idle} │               │  │V │ │R │ │S │ │Mem │  ← bldgs │
│  {security: idle} │               │  └──┘ └───┘ └──┘ └────┘         │
│  {memory: active} │               │   ● ●   ●     ●   ●  ← agents   │
│                   │               │  ~~~~ ◄── events ← particles    │
│  Flat. Static.    │               │                                  │
│  Text-only.       │               │  🌍  [Globe: flights, vessels]  │
└──────────────────┘               │   📱  [Phone AR overlay]        │
                                    │   🔊  [Spatial audio]           │
                                    └──────────────────────────────────┘
```

---

## 2. Current Architecture

### 2.1 Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                    VECTOR Dashboard (React + Vite + TS)          │
│                                                                 │
│  ┌────────┬───────────┬───────────────────┬──────────────────┐  │
│  │ Health │ Agent     │ Event Stream       │ Research        │  │
│  │ Score  │ Status    │ (scrolling log)    │ Results         │  │
│  │ 92/100 │ [list]    │                    │                 │  │
│  ├────────┼───────────┼───────────────────┼──────────────────┤  │
│  │ Memory │  Orb     │  Goal Progress    │  Quick Actions  │  │
│  │ Stats  │  (state) │                   │                  │  │
│  └────────┴──────────┴───────────────────┴──────────────────┘  │
│                                                                 │
│  Updates: WebSocket every 500ms -> React state                 │
│  No 3D, no animation, no audio, no AR                          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Files

| File | Role | Lines |
|------|------|-------|
| `dashboard/src/App.tsx` | Main app layout | ~200 |
| `dashboard/src/components/` | Panel components | variable |
| `dashboard/src/hooks/useWebSocket.ts` | WebSocket event stream | ~120 |
| `dashboard/src/stores/` | State management (zustand) | ~300 |
| `dashboard/src/pages/` | Page components | variable |
| `dashboard/package.json` | Dependencies | ~60 |
| `core/ui/` | UI comms from backend | ~400 |

### 2.3 WebSocket Event Stream

```typescript
// Current WebSocket events consumed by dashboard
interface WSEvent {
  type: "agent_status" | "event_log" | "health_update" | "goal_progress" | "research_result";
  payload: Record<string, unknown>;
}
```

---

## 3. Target Architecture

### 3.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        VECTOR Dashboard (Browser)                        │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                  3D City Scene (Three.js)                         │   │
│  │                                                                   │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐       │   │
│  │  │Voice│ │Resr │ │Sec  │ │Mem  │ │Karp │ │Ops  │ │Inf  │ ← bldgs│   │
│  │  │     │ │     │ │     │ │     │ │     │ │     │ │     │        │   │
│  │  │ ●─● │ │ ●   │ │ ●   │ │ ●─● │ │ ●   │ │ ●   │ │ ●   │ ← dots│   │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘       │   │
│  │  ~~~~ particle trails between buildings (events)                  │   │
│  │                                                                   │   │
│  │  ┌──────────────────────────────────────────────────────┐       │   │
│  │  │  Overlay Panels (React, draggable, modular)           │       │   │
│  │  │  ┌──────┐ ┌──────────┐ ┌──────────────┐             │       │   │
│  │  │  │Agent │ │Event Log │ │Globe (d3)    │             │       │   │
│  │  │  │List  │ │(scroll)  │ │              │             │       │   │
│  │  │  └──────┘ └──────────┘ └──────────────┘             │       │   │
│  │  └──────────────────────────────────────────────────────┘       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  WebXR AR Mode (phone):                                                  │
│    Phone camera sees Legion laptop → VECTOR city overlaid on screen     │
│    Floating agent cards in AR space                                      │
│                                                                          │
│  Spatial Audio:                                                          │
│    Voice district → front-left speaker                                   │
│    Security alert → rear-right direction                                 │
│    Agent activity → position = district building location                │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Tree

```
App
├── ThreeJSScene (R3F Canvas)
│   ├── CityEnvironment
│   │   ├── DistrictBuilding[7]  ← one per district
│   │   │   ├── BuildingMesh (height = HP, color = state)
│   │   │   ├── AgentDot (moving dot)
│   │   │   └── DistrictLabel (CSS2DRenderer text)
│   │   ├── ParticleSystem (event streams between buildings)
│   │   └── Ground (grid + reflective surface)
│   ├── WorldStateGlobe (d3-geo globe)
│   │   ├── FlightArcs (animated SVG/curves)
│   │   ├── VesselMarkers
│   │   ├── EarthquakePulse
│   │   └── ConflictZone
│   ├── CSS2DOverlays
│   │   ├── AgentActivityCard[hover]
│   │   └── DistrictTooltip
│   └── Controls (OrbitControls + auto-rotate)
├── ReactPanelOverlay
│   ├── AgentStatusPanel (modular, embeddable)
│   ├── EventLogPanel (modular, embeddable)
│   ├── GoalProgressPanel (modular, embeddable)
│   └── QuickActionsPanel (modular, embeddable)
├── SpatialAudioManager
│   ├── DistrictVoicePositioner
│   ├── AlertDirectionCue
│   └── AmbientSoundLayer
└── WebXRBridge
    ├── ARButton (enter AR mode)
    ├── ARSceneContent (phone AR scene)
    └── ARPlaneDetector (detect laptop screen)
```

### 3.3 Data Flow

```
core/loop/context_engine.py
    │  (14 domains → structured state)
    ▼
core/ui/websocket_broadcaster.py
    │  (enhanced events: agent positions, HP, events, globe data)
    ▼
dashboard/src/hooks/useVectorEvents.ts
    │  (typed WebSocket → zustand store → R3F)
    ▼
zustand stores:
    ├── useCityStore    → 3D scene state (districts, agents, HP)
    ├── useGlobeStore   → world state (flights, vessels, earthquakes)
    ├── useAudioStore   → spatial audio state
    └── useARStore      → WebXR AR state
```

### 3.4 Event Types (Enhanced WebSocket)

```typescript
// New/additional WebSocket events for 3D dashboard
interface WSEvent {
  type: "city_update" | "globe_update" | "agent_movement" | "event_particle" | "audio_cue";
  payload: Record<string, unknown>;
}

interface CityUpdateEvent {
  type: "city_update";
  payload: {
    districts: Array<{
      id: string;
      name: string;
      health: number;           // 0-100, used as building height and color
      agent_count: number;
      active_tasks: number;
      state: "idle" | "active" | "busy" | "error";
      position: { x: number; z: number };  // grid position in city
    }>;
    agents: Array<{
      id: string;
      name: string;
      district_id: string;
      state: string;
      position: { x: number; y: number; z: number };
    }>;
    events: Array<{
      id: string;
      from_district: string;
      to_district: string;
      type: string;
      timestamp: number;
    }>;
  };
}

interface GlobeUpdateEvent {
  type: "globe_update";
  payload: {
    flights: Array<{
      id: string;
      origin: [number, number];
      destination: [number, number];
      airline: string;
      altitude: number;
    }>;
    vessels: Array<{
      id: string;
      lat: number;
      lng: number;
      name: string;
      type: string;
    }>;
    earthquakes: Array<{
      id: string;
      lat: number;
      lng: number;
      magnitude: number;
      depth: number;
      timestamp: number;
    }>;
    conflicts: Array<{
      id: string;
      region: string;
      lat: number;
      lng: number;
      intensity: number;
    }>;
  };
}
```

---

## 4. Component Breakdown

### 4.1 ThreeJSCore

**File:** `dashboard/src/three/Scene.tsx` (new, ~300 lines)
**File:** `dashboard/src/three/CityEnvironment.tsx` (new, ~250 lines)
**File:** `dashboard/src/three/DistrictBuilding.tsx` (new, ~200 lines)

**Responsibility:** Renders the 3D city scene with districts as buildings, agents as moving dots, events as particle trails.

```typescript
// ── Scene.tsx ──
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Sky, Environment } from "@react-three/drei";

export function ThreeJSScene() {
  return (
    <Canvas camera={{ position: [30, 20, 30], fov: 50 }}>
      <Sky sunPosition={[100, 20, 100]} />
      <ambientLight intensity={0.4} />
      <directionalLight position={[10, 20, 10]} intensity={1.0} />
      <CityEnvironment />
      <WorldStateGlobe />
      <ParticleSystem />
      <OrbitControls
        enableDamping
        dampingFactor={0.05}
        autoRotate
        autoRotateSpeed={0.5}
        minDistance={10}
        maxDistance={80}
      />
      <EffectComposer>
        <Bloom luminanceThreshold={0.5} luminanceStrength={1.5} />
      </EffectComposer>
    </Canvas>
  );
}

// ── CityEnvironment.tsx ──
// District building configuration
const DISTRICT_LAYOUT = [
  { id: "voice", name: "Voice", position: [-8, 0, -5], color: "#6366f1" },
  { id: "research", name: "Research", position: [0, 0, -6], color: "#22c55e" },
  { id: "security", name: "Security", position: [8, 0, -5], color: "#ef4444" },
  { id: "memory", name: "Memory", position: [-5, 0, 2], color: "#a855f7" },
  { id: "karpathy", name: "Karpathy Lab", position: [5, 0, 2], color: "#f59e0b" },
  { id: "ops", name: "Ops", position: [-8, 0, 8], color: "#3b82f6" },
  { id: "inference", name: "Inference", position: [8, 0, 8], color: "#ec4899" },
];

export function CityEnvironment({ districtData }: { districtData: DistrictState[] }) {
  return (
    <group>
      {/* Ground plane with reflective surface */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.5, 0]}>
        <planeGeometry args={[40, 30]} />
        <meshStandardMaterial color="#1a1a2e" roughness={0.8} metalness={0.2} />
      </mesh>
      <gridHelper args={[40, 20, "#333355", "#222244"]} />
      
      {/* District buildings */}
      {DISTRICT_LAYOUT.map((layout) => {
        const district = districtData.find(d => d.id === layout.id);
        return (
          <DistrictBuilding
            key={layout.id}
            layout={layout}
            health={district?.health ?? 50}
            state={district?.state ?? "idle"}
            agentCount={district?.agent_count ?? 0}
            taskCount={district?.active_tasks ?? 0}
          />
        );
      })}
    </group>
  );
}

// ── DistrictBuilding.tsx ──
interface DistrictBuildingProps {
  layout: { id: string; name: string; position: [number, number, number]; color: string };
  health: number;
  state: "idle" | "active" | "busy" | "error";
  agentCount: number;
  taskCount: number;
}

export function DistrictBuilding({ layout, health, state, agentCount, taskCount }: DistrictBuildingProps) {
  const meshRef = useRef<Mesh>(null);
  const height = useSpring(health, { config: { mass: 1, tension: 80, friction: 20 } });
  
  // Color based on state
  const stateColor = {
    idle: layout.color,
    active: layout.color,
    busy: brighten(layout.color, 0.3),
    error: "#ef4444",
  };
  
  // Animate height with spring physics
  const scaleY = 0.5 + (health / 100) * 4.5;  // 0.5 to 5.0 scale
  
  return (
    <group position={[layout.position[0], 0, layout.position[2]]}>
      {/* Main building mesh */}
      <animated.mesh ref={meshRef} scale-y={scaleY}>
        <boxGeometry args={[2, 1, 2]} />
        <meshPhysicalMaterial
          color={stateColor[state]}
          transparent
          opacity={0.85}
          roughness={0.3}
          metalness={0.6}
          emissive={state === "active" ? layout.color : "#000000"}
          emissiveIntensity={state === "active" ? 0.3 : 0}
        />
      </animated.mesh>
      
      {/* District label (CSS2DRenderer) */}
      <Html position={[0, scaleY + 0.8, 0]} center>
        <div className="district-label">
          <span>{layout.name}</span>
          <span className="hp-indicator">{health}%</span>
        </div>
      </Html>
      
      {/* Agent dots orbiting the building */}
      {Array.from({ length: agentCount }).map((_, i) => (
        <AgentDot
          key={i}
          index={i}
          total={agentCount}
          orbitRadius={1.5 + Math.random() * 0.5}
          speed={0.5 + Math.random() * 0.3}
          color={layout.color}
        />
      ))}
      
      {/* Task activity ring */}
      {taskCount > 0 && (
        <RingPulse
          radius={1.2}
          speed={0.2 + taskCount * 0.05}
          opacity={0.3 + taskCount * 0.1}
        />
      )}
    </group>
  );
}
```

**City visualization rules:**

```typescript
// Building height = district health (HP) → 0-100 scale mapped to 0.5-5.0
// Building color = district state:
//   idle: base color, no emission
//   active: base color, slight emission pulse
//   busy: brightened color, strong emission pulse
//   error: red, pulsing emission
// Agent dots = small spheres orbiting their district building
//   orbit speed = task activity level
//   color = district color
// Event particles = thin trails between district buildings
//   color = source district
//   speed = event priority
// Ground = dark grid with subtle reflection
```

### 4.2 WorldStateGlobe

**File:** `dashboard/src/three/WorldStateGlobe.tsx` (new, ~300 lines)

**Responsibility:** 3D globe showing Shadowbroker intel — flights, vessels, earthquakes, conflicts in real-time.

```typescript
export function WorldStateGlobe({ data }: { data: GlobeData }) {
  const globeRef = useRef<Mesh>(null);
  
  // Auto-rotate slowly
  useFrame((_, delta) => {
    if (globeRef.current) {
      globeRef.current.rotation.y += delta * 0.05;
    }
  });
  
  return (
    <group position={[0, 3, -12]} scale={0.35}>
      {/* Globe sphere */}
      <mesh ref={globeRef}>
        <sphereGeometry args={[5, 64, 64]} />
        <meshPhongMaterial
          map={useLoader(TextureLoader, "/textures/earth_day.jpg")}
          bumpMap={useLoader(TextureLoader, "/textures/earth_bump.jpg")}
          bumpScale={0.05}
          specularMap={useLoader(TextureLoader, "/textures/earth_spec.jpg")}
          specular={new Color("#333333")}
        />
      </mesh>
      
      {/* Atmosphere glow */}
      <mesh>
        <sphereGeometry args={[5.1, 64, 64]} />
        <meshPhongMaterial
          transparent
          opacity={0.1}
          color="#4488ff"
          side={BackSide}
        />
      </mesh>
      
      {/* Flight arcs */}
      {data.flights.map((flight) => (
        <FlightArc
          key={flight.id}
          origin={flight.origin}
          destination={flight.destination}
          progress={flight.progress}
        />
      ))}
      
      {/* Vessel markers */}
      {data.vessels.map((vessel) => (
        <VesselMarker key={vessel.id} lat={vessel.lat} lng={vessel.lng} />
      ))}
      
      {/* Earthquake pulses */}
      {data.earthquakes.map((eq) => (
        <EarthquakePulse
          key={`${eq.lat}-${eq.lng}-${eq.timestamp}`}
          lat={eq.lat}
          lng={eq.lng}
          magnitude={eq.magnitude}
        />
      ))}
      
      {/* Conflict zones */}
      {data.conflicts.map((conflict) => (
        <ConflictZone
          key={conflict.region}
          lat={conflict.lat}
          lng={conflict.lng}
          intensity={conflict.intensity}
        />
      ))}
    </group>
  );
}
```

**Globe rendering implementation:**

```typescript
// ── Flight Arc ──
// Great-circle arc between origin and destination airports
// Animated: dotted line moves from origin to destination
// Color: airline color or default gold
// Click: shows flight details (flight number, altitude, ETA)

// ── Vessel Marker ──
// Small dot at vessel position
// Color by type: cargo=blue, tanker=red, passenger=green
// Size by tonnage
// Click: vessel details (name, flag, speed, destination)

// ── Earthquake Pulse ──
// Expanding ring at epicenter
// Size and intensity by magnitude
// Color by depth: shallow=red, mid=orange, deep=yellow
// Duration: 5s then fade
// Shockwave effect via animated circle geometry

// ── Conflict Zone ──
// Pulsing polygon at region
// Color by intensity: green=low, yellow=medium, red=high
// Click: conflict summary from Shadowbroker
// Duration: persistent while conflict active
```

**Coordinate projection helper:**

```typescript
// Convert lat/lng to 3D position on globe
function latLngToPosition(lat: number, lng: number, radius: number = 5): [number, number, number] {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lng + 180) * (Math.PI / 180);
  const x = -radius * Math.sin(phi) * Math.cos(theta);
  const y = radius * Math.cos(phi);
  const z = radius * Math.sin(phi) * Math.sin(theta);
  return [x, y, z];
}
```

### 4.3 WebXRBridge

**File:** `dashboard/src/ar/WebXRBridge.tsx` (new, ~200 lines)
**File:** `dashboard/src/ar/ARScene.tsx` (new, ~250 lines)

**Responsibility:** Phone AR mode — point phone camera at Legion laptop to see VECTOR city model overlaid on the screen, agent activity as floating cards.

```typescript
// ── WebXRBridge.tsx ──
export function WebXRBridge() {
  const { isARSupported, enterAR } = useARMode();
  
  if (!isARSupported) {
    return null; // Hidden on desktop
  }
  
  return (
    <div className="ar-bridge">
      <ARButton onClick={enterAR}>
        📱 View in AR
      </ARButton>
      <p className="ar-instruction">
        Point your phone at your Legion laptop to see VECTOR city overlaid
      </p>
    </div>
  );
}

// ── ARScene.tsx ──
// Uses @react-three/xr for WebXR immersion
// When phone enters AR mode:
// 1. Camera feed starts (phone sees real world)
// 2. VECTOR city model renders on detected planes (hit-test laptop screen)
// 3. Agent activity appears as floating cards in AR space
// 4. User can walk around the city, see it from any angle

export function ARScene() {
  const { session } = useXR();
  const { districtData, agentData } = useCityStore();
  
  return (
    <>
      {/* Hit-test to find laptop screen surface */}
      <ARPlaneDetector onPlaneFound={(plane) => {
        // Position city model on detected surface
      }} />
      
      {/* Scaled-down city model in AR */}
      <group position={[0, 0, -1.5]} scale={0.3}>
        <CityEnvironment districtData={districtData} />
      </group>
      
      {/* Floating agent cards */}
      {agentData.map((agent) => (
        <AgentARCard
          key={agent.id}
          agent={agent}
          position={[Math.random() * 2 - 1, Math.random() * 1.5 + 0.5, -2]}
        />
      ))}
    </>
  );
}

interface AgentARCardProps {
  agent: Agent;
  position: [number, number, number];
}

function AgentARCard({ agent, position }: AgentARCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  
  return (
    <group position={position}>
      {/* Card background */}
      <mesh
        onPointerEnter={() => setIsHovered(true)}
        onPointerLeave={() => setIsHovered(false)}
      >
        <planeGeometry args={[0.8, 0.4]} />
        <meshBasicMaterial
          color={isHovered ? "#ffffff" : "#222244"}
          transparent
          opacity={0.85}
        />
      </mesh>
      
      {/* Agent name */}
      <Html position={[0, 0.05, 0.001]} center>
        <div className="ar-agent-card">
          <div className="agent-name">{agent.name}</div>
          <div className="agent-status">{agent.state}</div>
        </div>
      </Html>
    </group>
  );
}
```

### 4.4 SpatialAudio

**File:** `dashboard/src/audio/SpatialAudioManager.ts` (new, ~200 lines)

**Responsibility:** WebAudio positional audio — voice comes from direction of active district, alerts from fixed position.

```typescript
export class SpatialAudioManager {
  private ctx: AudioContext;
  private listener: AudioListener;
  private sources: Map<string, AudioSource>;
  
  constructor(cameraPosition: () => [number, number, number]) {
    this.ctx = new AudioContext();
    this.listener = new AudioListener();
    this.sources = new Map();
    
    // Connect listener to camera position
    // This makes audio direction relative to user's viewing angle
  }
  
  registerDistrictVoice(districtId: string, position: [number, number, number]): void {
    // Create panner node for this district
    const panner = this.ctx.createPanner();
    panner.panningModel = "HRTF";
    panner.distanceModel = "inverse";
    panner.refDistance = 1;
    panner.maxDistance = 20;
    panner.rolloffFactor = 2;
    panner.setPosition(position[0], position[1], position[2]);
    
    // Store for later use
    this.sources.set(districtId, {
      panner,
      gain: this.ctx.createGain(),
      isPlaying: false,
    });
  }
  
  playDistrictVoice(districtId: string, audioUrl: string): void {
    const source = this.sources.get(districtId);
    if (!source) return;
    
    // Load audio and play through district's panner
    fetch(audioUrl)
      .then(r => r.arrayBuffer())
      .then(buffer => this.ctx.decodeAudioData(buffer))
      .then(audioBuffer => {
        const bufferSource = this.ctx.createBufferSource();
        bufferSource.buffer = audioBuffer;
        bufferSource.connect(source.panner);
        source.panner.connect(this.ctx.destination);
        bufferSource.start();
        source.isPlaying = true;
      });
  }
  
  playAlert(direction: "front" | "left" | "right" | "rear"): void {
    // Play alert tone from fixed direction
    const positions = {
      front: [0, 0, -3],
      left: [-3, 0, 0],
      right: [3, 0, 0],
      rear: [0, 0, 3],
    };
    
    // Create temporary panner at alert position
    // Play alert sound effect through it
    // Then clean up
  }
  
  playAmbientLayer(type: "city_hum" | "data_flow" | "silent_night"): void {
    // Background ambient audio
    // city_hum: subtle drone representing active city
    // data_flow: quiet clicks and data sounds
    // silent_night: minimal ambient when idle
  }
  
  updateListenerPosition(pos: [number, number, number]): void {
    this.listener.setPosition(pos[0], pos[1], pos[2]);
    this.listener.setOrientation(
      // Camera forward direction
      0, 0, -1,
      // Camera up direction
      0, 1, 0,
    );
  }
}
```

**District-to-speaker mapping:**

```
District positions in 3D scene:
  Voice:      [-8, 0, -5]  → front-left speaker
  Research:   [0, 0, -6]   → center speaker
  Security:   [8, 0, -5]   → front-right speaker
  Memory:     [-5, 0, 2]   → left speaker
  Karpathy:   [5, 0, 2]    → right speaker
  Ops:        [-8, 0, 8]   → rear-left (surround)
  Inference:  [8, 0, 8]    → rear-right (surround)

When user rotates the 3D camera:
  Audio positions update relative to camera angle
  → HRTF panning creates realistic 3D audio
  → Closing eyes, user can point to which district is speaking
```

### 4.5 DashboardRefactor

**File:** `dashboard/src/panels/AgentStatusPanel.tsx` (refactored, ~150 lines)
**File:** `dashboard/src/panels/EventLogPanel.tsx` (refactored, ~150 lines)
**File:** `dashboard/src/panels/GoalProgressPanel.tsx` (refactored, ~100 lines)
**File:** `dashboard/src/panels/QuickActionsPanel.tsx` (refactored, ~100 lines)
**File:** `dashboard/src/panels/PanelContainer.tsx` (new, ~100 lines)

**Responsibility:** Modularize current dashboard into pluggable panels that the Three.js scene can embed.

```typescript
// ── PanelContainer.tsx ──
// Provides drag-to-reorder, minimize, embed-in-3D toggle

interface PanelConfig {
  id: string;
  component: React.ComponentType<PanelProps>;
  defaultPosition: { x: number; y: number };
  defaultSize: { width: number; height: number };
  embeddableIn3D: boolean;
  minifiedView: boolean;
}

export function PanelContainer({ config, children }: { config: PanelConfig; children: React.ReactNode }) {
  const { embedPanel } = useCityStore();
  
  return (
    <Rnd
      defaultPosition={config.defaultPosition}
      defaultSize={config.defaultSize}
      minWidth={200}
      minHeight={100}
      dragHandleClassName="panel-header"
    >
      <div className="panel">
        <div className="panel-header">
          <span>{config.id}</span>
          <div className="panel-controls">
            {config.embeddableIn3D && (
              <button onClick={() => embedPanel(config.id)}>
                🏙 Embed in 3D
              </button>
            )}
            <button onClick={minimize}>_</button>
            <button onClick={close}>×</button>
          </div>
        </div>
        <div className="panel-content">
          {children}
        </div>
      </div>
    </Rnd>
  );
}
```

---

## 5. Agent Dispatch Plan

### 5.1 Agent A: Three.js Scene + City Visualization + Agent Animation

**Scope:**
- `dashboard/src/three/Scene.tsx` — R3F Canvas setup with lighting, sky, effects
- `dashboard/src/three/CityEnvironment.tsx` — District layout, building generation
- `dashboard/src/three/DistrictBuilding.tsx` — Animated building mesh with HP-based height
- `dashboard/src/three/AgentDot.tsx` — Orbiting agent indicator
- `dashboard/src/three/ParticleSystem.tsx` — Event particle trails
- `dashboard/src/hooks/useCityStore.ts` — Zustand store for city state
- `dashboard/src/hooks/useVectorEvents.ts` — Enhanced WebSocket hook
- CSS files for labels and overlays
- Performance optimization (instanced meshes, LOD)

**Deliverables:**
1. 3D scene rendering 7 district buildings with HP-based height animation
2. Agent dots orbiting each district building with spring physics
3. Particle trails representing event streams between districts
4. State-dependent colors and emissive effects (idle/active/busy/error)
5. OrbitControls with auto-rotate, zoom, and damping
6. Bloom post-processing for glow effects
7. 60fps performance on RTX 5070 Ti

### 5.2 Agent B: World State Globe + WebXR AR Mode

**Scope:**
- `dashboard/src/three/WorldStateGlobe.tsx` — 3D globe with earth textures
- `dashboard/src/three/FlightArc.tsx` — Animated flight arcs
- `dashboard/src/three/VesselMarker.tsx` — Vessel position markers
- `dashboard/src/three/EarthquakePulse.tsx` — Expanding ring animations
- `dashboard/src/three/ConflictZone.tsx` — Pulsing conflict polygons
- `dashboard/src/hooks/useGlobeStore.ts` — Zustand store for globe data
- `dashboard/src/ar/WebXRBridge.tsx` — AR entry point
- `dashboard/src/ar/ARScene.tsx` — AR scene content
- `dashboard/src/ar/ARPlaneDetector.tsx` — Plane detection for laptop screen

**Deliverables:**
1. 3D globe with Earth texture, auto-rotation, atmosphere glow
2. Animated flight arcs between origin/destination with progress
3. Vessel markers with type-based coloring and click details
4. Earthquake pulse animations (expanding rings with depth color)
5. Conflict zone polygons with intensity-based color
6. WebXR AR mode entry on phone browsers
7. AR city overlay on detected planes
8. Floating agent cards in AR space

### 5.3 Agent C: Spatial Audio + Dashboard Modularization

**Scope:**
- `dashboard/src/audio/SpatialAudioManager.ts` — WebAudio positional audio
- `dashboard/src/audio/DistrictVoicePositioner.ts` — Voice routing to speaker positions
- `dashboard/src/audio/AlertDirectionCue.ts` — Alert audio from fixed directions
- `dashboard/src/panels/PanelContainer.tsx` — Draggable panel wrapper
- `dashboard/src/panels/AgentStatusPanel.tsx` — Refactored modular panel
- `dashboard/src/panels/EventLogPanel.tsx` — Refactored modular panel
- `dashboard/src/panels/GoalProgressPanel.tsx` — Refactored modular panel
- `dashboard/src/panels/QuickActionsPanel.tsx` — Refactored modular panel
- `dashboard/src/hooks/useAudioStore.ts` — Audio state store
- `dashboard/src/App.tsx` — Refactored to compose panels

**Deliverables:**
1. SpatialAudioManager with HRTF panning per district
2. District voice positioner — VECTOR's voice comes from active district direction
3. Alert direction cues — security alerts from rear, health from center
4. Ambient audio layer (city hum, data flow sounds)
5. PanelContainer with drag-to-reorder, minimize, embed toggle
6. All existing panels refactored to pluggable architecture
7. Panel embed mode — panel renders inside 3D scene as textured quad
8. Zustand stores for panel layout persistence

---

## 6. Implementation Steps

### 6.1 Phase 1: 3D City Foundation (Agent A)

**Step 1.1: Set up Three.js project**

- [ ] Install dependencies: `@react-three/fiber`, `@react-three/drei`, `three`, `@types/three`, `postprocessing`
- [ ] Create `dashboard/src/three/` directory
- [ ] Create `Scene.tsx` with Canvas, lighting, Sky, OrbitControls

**Step 1.2: Build city environment**

- [ ] Create `CityEnvironment.tsx` with district layout grid
- [ ] Create `DistrictBuilding.tsx` with animated height based on HP
- [ ] Implement state-based colors and emissive glow
- [ ] Add district labels using CSS2DRenderer

**Step 1.3: Add agent visualization**

- [ ] Create `AgentDot.tsx` with orbiting animation
- [ ] Implement spring physics for smooth transitions
- [ ] Add hover tooltip showing agent details

**Step 1.4: Add particle system**

- [ ] Create `ParticleSystem.tsx` for event streams
- [ ] Particle color = source district color
- [ ] Particle speed = event priority

**Step 1.5: Add post-processing**

- [ ] Add Bloom effect for glow
- [ ] Add SSR (screen space reflections) for ground
- [ ] Performance tuning: instanced meshes for agent dots

**Step 1.6: Create data stores**

- [ ] Create `useCityStore.ts` with zustand
- [ ] Create `useVectorEvents.ts` WebSocket hook
- [ ] Wire real data from backend

**Step 1.7: Test performance**

- [ ] Verify 60fps on RTX 5070 Ti with 7 buildings + 50 agents + 200 particles
- [ ] Profile with Chrome DevTools performance tab
- [ ] Implement LOD for distant buildings

### 6.2 Phase 2: Globe + WebXR (Agent B)

**Step 2.1: Build 3D globe**

- [ ] Create `WorldStateGlobe.tsx` with Earth texture
- [ ] Add atmosphere glow effect
- [ ] Implement lat/lng → 3D position projection

**Step 2.2: Add globe data layers**

- [ ] Create `FlightArc.tsx` with animated dotted lines
- [ ] Create `VesselMarker.tsx` with type-based coloring
- [ ] Create `EarthquakePulse.tsx` with expanding ring
- [ ] Create `ConflictZone.tsx` with pulsing polygon
- [ ] Create `useGlobeStore.ts` for data

**Step 2.3: Add interactivity**

- [ ] Click on flight → show details (airline, altitude, route)
- [ ] Click on vessel → show name, flag, speed
- [ ] Click on conflict → show Shadowbroker intel summary
- [ ] Globe auto-rotation with manual override

**Step 2.4: Implement WebXR AR**

- [ ] Create `WebXRBridge.tsx` with AR support detection
- [ ] Create `ARScene.tsx` with @react-three/xr
- [ ] Implement hit-test for plane detection
- [ ] Scale city model for AR
- [ ] Add floating agent cards

**Step 2.5: Test AR**

- [ ] Test WebXR on phone browser (Chrome Android)
- [ ] Verify city overlay on laptop screen detection
- [ ] Verify agent cards float in AR space
- [ ] Test performance on phone (target 30fps AR)

### 6.3 Phase 3: Spatial Audio + Dashboard (Agent C)

**Step 3.1: Implement SpatialAudioManager**

- [ ] Create `SpatialAudioManager.ts`
- [ ] Implement AudioContext + AudioListener setup
- [ ] Create PannerNode per district
- [ ] Implement position updates relative to camera

**Step 3.2: Add audio features**

- [ ] Create `DistrictVoicePositioner.ts` — route TTS to district's panner
- [ ] Create `AlertDirectionCue.ts` — play alert from fixed directions
- [ ] Create ambient audio layer (subtle city hum)
- [ ] Create `useAudioStore.ts` for state

**Step 3.3: Modularize dashboard**

- [ ] Create `PanelContainer.tsx` with drag-to-reorder
- [ ] Refactor `AgentStatusPanel.tsx` to remove hardcoded layout
- [ ] Refactor `EventLogPanel.tsx` to modular component
- [ ] Refactor `GoalProgressPanel.tsx` to modular component
- [ ] Refactor `QuickActionsPanel.tsx` to modular component

**Step 3.4: Implement panel embedding**

- [ ] Add "Embed in 3D" toggle to PanelContainer
- [ ] Renders panel content on textured quad in 3D scene
- [ ] Panel floats near its related district building
- [ ] Persist panel layout in localStorage

**Step 3.5: Refactor App.tsx**

- [ ] Compose Scene + panels + audio
- [ ] Add AR mode toggle
- [ ] Add 2D/3D view toggle (fallback for non-WebGL browsers)
- [ ] Test all existing dashboard features still work

---

## 7. Files to Create/Modify

### Create:

| File | Lines | Purpose |
|------|-------|---------|
| `dashboard/src/three/Scene.tsx` | ~300 | R3F Canvas with lighting, Sky, effects |
| `dashboard/src/three/CityEnvironment.tsx` | ~250 | District layout, building generation |
| `dashboard/src/three/DistrictBuilding.tsx` | ~200 | Animated building mesh |
| `dashboard/src/three/AgentDot.tsx` | ~100 | Orbiting agent indicator |
| `dashboard/src/three/ParticleSystem.tsx` | ~150 | Event particle trails |
| `dashboard/src/three/WorldStateGlobe.tsx` | ~300 | 3D earth globe with data layers |
| `dashboard/src/three/FlightArc.tsx` | ~100 | Animated flight arcs |
| `dashboard/src/three/VesselMarker.tsx` | ~80 | Vessel position markers |
| `dashboard/src/three/EarthquakePulse.tsx` | ~80 | Expanding ring animations |
| `dashboard/src/three/ConflictZone.tsx` | ~80 | Pulsing conflict polygons |
| `dashboard/src/ar/WebXRBridge.tsx` | ~200 | AR mode entry point |
| `dashboard/src/ar/ARScene.tsx` | ~250 | WebXR AR scene content |
| `dashboard/src/ar/ARPlaneDetector.tsx` | ~100 | Plane detection for laptop |
| `dashboard/src/audio/SpatialAudioManager.ts` | ~200 | WebAudio positional audio |
| `dashboard/src/audio/DistrictVoicePositioner.ts` | ~100 | Voice routing per district |
| `dashboard/src/audio/AlertDirectionCue.ts` | ~80 | Alert audio from directions |
| `dashboard/src/panels/PanelContainer.tsx` | ~100 | Draggable panel wrapper |
| `dashboard/src/hooks/useCityStore.ts` | ~100 | City state zustand store |
| `dashboard/src/hooks/useGlobeStore.ts` | ~100 | Globe data zustand store |
| `dashboard/src/hooks/useAudioStore.ts` | ~60 | Audio state zustand store |
| `dashboard/src/hooks/useVectorEvents.ts` | ~200 | Enhanced WebSocket hook |
| `dashboard/src/styles/three-dashboard.css` | ~200 | 3D scene CSS styles |

### Modify:

| File | Change |
|------|--------|
| `dashboard/src/App.tsx` | Compose 3D scene + panels + audio |
| `dashboard/package.json` | Add three, @react-three/fiber, @react-three/drei, @react-three/xr, zustand |
| `dashboard/vite.config.ts` | Add WebXR required headers |
| `dashboard/src/panels/AgentStatusPanel.tsx` | Refactor to modular panel |
| `dashboard/src/panels/EventLogPanel.tsx` | Refactor to modular panel |
| `dashboard/src/panels/GoalProgressPanel.tsx` | Refactor to modular panel |
| `dashboard/src/panels/QuickActionsPanel.tsx` | Refactor to modular panel |
| `core/ui/websocket_broadcaster.py` | Add city_update, globe_update events |

---

## 8. Success Criteria

### 8.1 Measurable Metrics

| Criterion | Current | Target | Measurement Method |
|-----------|---------|--------|-------------------|
| 3D city render framerate | N/A | 60fps on RTX 5070 Ti | Chrome DevTools FPS meter, 60s average |
| 3D city render (integrated GPU) | N/A | 30fps fallback | Test on integrated GPU, enable LOD |
| WebXR AR framerate | N/A | 30fps on phone | WebXR FPS counter |
| District building HP→height accuracy | N/A | ±5% of real HP | Compare building height to zustand HP value |
| Agent dot count | N/A | 50+ at 60fps | Increment agent count until fps drops below 55 |
| Globe flight arc count | N/A | 200+ arcs at 60fps | Count of rendered flight arcs |
| Spatial audio direction accuracy | N/A | <15deg | Listener test: can point to active district by sound |
| AR plane detection | N/A | <3s | Time from AR start to city overlay visible |
| Dashboard panel drag latency | N/A | <16ms | Measure drag response time |
| WebSocket event → visualization | ~500ms | <200ms | Measure from backend emit to scene update |
| Embed panel in 3D render | N/A | <5ms overhead | FPS with vs without embedded panel |

### 8.2 Functional Criteria

1. 3D city loads within 3s on Legion laptop (bundle + textures)
2. Building height animates smoothly when district HP changes
3. Agent dots orbit with smooth spring physics
4. Event particles flow between districts when events occur
5. Globe auto-rotates and shows real flight/vessel/earthquake/conflict data
6. Clicking on globe markers shows details tooltip
7. WebXR AR mode works on Chrome Android (phone camera + overlay)
8. AR mode detects laptop screen surface and places city model
9. Spatial audio: voice from Voice district comes from front-left speaker
10. Security alert audio comes from rear-right direction
11. All dashboard panels still work in 2D fallback mode
12. Panel layout persists across browser sessions (localStorage)

### 8.3 Backward Compatibility

1. All existing dashboard panels work in 2D mode (non-WebGL browsers)
2. Existing WebSocket events still handled (city_update is additive)
3. All existing React tests pass
4. Panel data still accessible from zustand stores (not just 3D)
5. Mobile browser gets simplified 2D view (no WebGL degradation)

---

## 9. Dependencies

### 9.1 External Packages

```json
// Add to dashboard/package.json:
{
  "dependencies": {
    "three": "^0.170.0",
    "@react-three/fiber": "^8.17.0",
    "@react-three/drei": "^9.114.0",
    "@react-three/xr": "^6.1.0",
    "@react-three/postprocessing": "^2.16.0",
    "zustand": "^4.5.0",
    "react-rnd": "^10.4.0"
  },
  "devDependencies": {
    "@types/three": "^0.170.0"
  }
}
```

### 9.2 Hardware Requirements

- **RTX 5070 Ti (12GB):** 60fps 3D scene with bloom, globe, 50+ agents, 200+ particles
- **Phone (WebXR AR):** Chrome Android on supported device (Android 10+)
- **Speakers/Headphones:** Required for spatial audio (stereo or surround)

### 9.3 Internal Dependencies

1. **specs-02 (Event Bus):** The `city_update` and `globe_update` events should ultimately flow through the event bus. Until specs-02 is implemented, use direct WebSocket broadcasting from `core/ui/`.
2. **Shadowbroker:** The WorldStateGlobe requires Shadowbroker data (flights, vessels, earthquakes, conflicts). Already assumed deployed. If not, globe renders with sample data.
3. **Autonomous loop agent state:** The city visualization requires real-time agent state (HP, activity, position). Already available from `context_engine.py`.

### 9.4 Asset Downloads

```bash
# Earth textures (for WorldStateGlobe):
# Download to dashboard/public/textures/:
#   earth_day.jpg        — 2048x1024, NASA Blue Marble
#   earth_bump.jpg       — 2048x1024, elevation map
#   earth_spec.jpg       — 2048x1024, specular map
#   earth_clouds.png     — 2048x1024, cloud layer (optional)
#
# Sources:
#   https://www.solarsystemscope.com/textures/
#   https://visibleearth.nasa.gov/
```

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Three.js bundle too large (>5MB) | High | Medium | Tree-shaking, dynamic imports, CDN for three.js |
| WebXR not supported on user's phone | Medium | Low | Graceful fallback to 2D dashboard |
| Spatial audio latency/jitter | Medium | Medium | Use low-latency AudioContext, pre-buffer alert sounds |
| Dashboard performance regression | Medium | High | Panel system is opt-in; existing flat dashboard still works |
| Globe texture loading slow on mobile | High | Low | Lazy load globe; use low-res fallback textures |
| AR hit-test fails on glossy laptop screen | Medium | Medium | Show AR position indicator; user manually places city |
| Three.js bundle breaks on older Safari | Low | High | Feature-detect WebGL2; show 2D fallback |
| zustand store conflicts with existing state | Low | Medium | Namespace stores; no shared state with existing code |

---

## 11. Appendix: 3D Scene Layout Diagram

```
Top-down view of VECTOR City:

        Z (-)
         │
         │
  Voice  │  Research   Security
  (-8,-5)│  (0,-6)     (8,-5)
         │
─────────┼───────────────────── X
         │
  Memory │              Karpathy
  (-5,2) │              (5,2)
         │
  Ops    │              Inference
  (-8,8) │              (8,8)
         │
         │
         │  Globe
         │  (0, 3, -12)

Camera default: (30, 20, 30) — isometric view
Ground: 40x30 units, dark grid
Building base: 2x2 units, height = 0.5 + (HP/100) * 4.5
```

### Animation Specifications

```typescript
// Building height animation (spring physics)
{
  mass: 1,
  tension: 80,    // stiffness
  friction: 20,   // damping
}

// Agent dot orbit
{
  radius: 1.5 + Math.random() * 0.5,
  speed: 0.5 + Math.random() * 0.3,  // radians/sec
  yOffset: 0.3 + Math.random() * 0.5,  // vertical oscillation
}

// Particle (event stream)
{
  lifetime: 2.0,        // seconds
  speed: 3.0,           // units/sec
  size: { start: 0.3, end: 0.05 },
  opacity: { start: 0.8, end: 0 },
  trailLength: 10,      // number of previous positions to draw
}

// Globe rotation
{
  autoRotateSpeed: 0.05,  // radians/sec
  interactionDamping: 0.95, // how quickly rotation returns after drag
}

// Earthquake pulse
{
  expandSpeed: 2.0,      // radius growth per second
  maxRadius: 1.0 + magnitude * 0.2,
  duration: 5.0,         // seconds
  opacity: { start: 0.6, end: 0 },
}
```
