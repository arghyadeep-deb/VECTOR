# VECTOR HUD Dashboard — Single-File Implementation Plan

> **For agentic workers:** Single HTML file, built section by section.

**Goal:** Build a standalone JARVIS-style VECTOR dashboard in one HTML file

**Architecture:** Single HTML with inline CSS/JS. Canvas 2D for orb visualization + particles. CSS animations for rings, scanlines, shimmer. JS for live clock, simulated data, event feed.

**Tech Stack:** HTML5, CSS3, Canvas 2D, Google Fonts (Share Tech Mono)

---

### Task 1: HTML skeleton + base styles + scanline overlay

- [ ] **Step 1: Write the HTML structure and CSS reset**

Create `core/ui/dashboard/index.html` with:
- DOCTYPE, viewport meta, Google Fonts link for Share Tech Mono
- Body with `#050d1a` background, no margins/padding, overflow hidden
- Scanline overlay using `::after` pseudo with repeating linear gradient
- 100vh, 100vw, flex column layout
- CSS variables for the color palette

- [ ] **Step 2: Verify no visual glitches**

Open in browser — should show solid dark background with subtle scanlines

- [ ] **Step 3: Commit**

### Task 2: Top Status Bar

- [ ] **Step 1: Write TopBar HTML+CSS**

Fixed height ~40px bar at top:
- Left: triangle icon (CSS shape or Unicode ▲) + "V.E.C.T.O.R." text in cyan
- Green dot + "ONLINE" badge
- Center: UPTIME, AGENTS count, VERSION labels with values
- Right: live clock placeholder `<span id="clock">`
- Glass morphism background, bottom border glow

- [ ] **Step 2: Add clock JS**

```js
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toTimeString().split(' ')[0];
}
setInterval(updateClock, 1000);
updateClock();
```

- [ ] **Step 3: Commit**

### Task 3: Left Column — Event Feed + Telemetry

- [ ] **Step 1: Build left panel (~280px)**

HTML structure:
- Top section: EVENT FEED heading with TICKER badge and blinking dot
- Scrollable `<div id="feed">` container
- Divider
- Bottom section: TELEMETRY with circular gauges (SVG arcs for MEM LOAD, CPU), AGENTS ALIVE counter, MEMORY ev count, SYSTEM HP number, MODE pills

CSS:
- Glass panel with corner brackets
- Left border glow per event row (color matches tag)
- Scroll container with custom scrollbar styling

- [ ] **Step 2: Event feed JS**

```js
const tags = ['CHAT', 'GOVE', 'SYS', 'ERROR'];
const tagColors = { CHAT: '#00d4ff', GOVE: '#ffaa00', SYS: '#ffffff', ERROR: '#ff3333' };
const messages = [
  'Agent GitBot HP restored +30',
  'Council decision stored to memory',
  'Morning brief generated',
  'Memory compaction complete',
  'District research query resolved',
];

function addEvent() {
  const tag = tags[Math.floor(Math.random() * tags.length)];
  const msg = messages[Math.floor(Math.random() * messages.length)];
  const time = new Date().toTimeString().split(' ')[0];
  const row = document.createElement('div');
  row.className = 'event-row';
  row.style.borderLeftColor = tagColors[tag];
  row.innerHTML = `<span class="ev-time">${time}</span> <span class="ev-tag" style="color:${tagColors[tag]}">[${tag}]</span> ${msg}`;
  document.getElementById('feed').appendChild(row);
  document.getElementById('feed').scrollTop = document.getElementById('feed').scrollHeight;
}
setInterval(addEvent, 3000);
// Seed initial events
for (let i = 0; i < 8; i++) addEvent();
```

- [ ] **Step 3: Circular gauge SVG**

SVG arc path math for MEM and CPU gauges (0-100%, stroke-dasharray based). CSS animation for the arc fill.

- [ ] **Step 4: Commit**

### Task 4: Center — Orb Visualization (Canvas)

- [ ] **Step 1: Canvas setup**

Full center area canvas with:
- Particle field (150 stars, random position/radius, slow drift using requestAnimationFrame)
- Central orb: radial gradient circle with breathing scale (sin wave on radius)

```js
const canvas = document.getElementById('orb-canvas');
const ctx = canvas.getContext('2d');
let time = 0;

const particles = Array.from({length: 150}, () => ({
  x: Math.random() * canvas.width,
  y: Math.random() * canvas.height,
  r: Math.random() * 1.5 + 0.5,
  vx: (Math.random() - 0.5) * 0.3,
  vy: (Math.random() - 0.5) * 0.3,
}));

function drawOrb() {
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;
  const breath = 1 + Math.sin(time * 0.001) * 0.03;
  const r = 60 * breath;

  // Glow
  const glow = ctx.createRadialGradient(cx, cy, r * 0.5, cx, cy, r * 3);
  glow.addColorStop(0, 'rgba(0, 212, 255, 0.15)');
  glow.addColorStop(1, 'rgba(0, 212, 255, 0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 3, 0, Math.PI * 2);
  ctx.fill();

  // Core
  const grad = ctx.createRadialGradient(cx - r * 0.3, cy - r * 0.3, 0, cx, cy, r);
  grad.addColorStop(0, '#ffffff');
  grad.addColorStop(0.4, '#aaddff');
  grad.addColorStop(1, '#00d4ff');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
}
```

- [ ] **Step 2: Orbital rings (CSS 3D transforms)**

Three `<div>` ring elements positioned absolutely over the canvas:
- Ring 1: `rotateX(75deg) rotateZ(0deg)` — 8s rotation
- Ring 2: `rotateX(60deg) rotateY(20deg)` — 13s rotation  
- Ring 3: `rotateX(80deg) rotateY(45deg)` — 20s rotation, opposite direction

Each ring is a CSS border ellipse with cyan glow, `border-radius: 50%`, `transform-style: preserve-3d`.

- [ ] **Step 3: Orb state colors**

Orb color shift based on state (idle=cyan, thinking=amber, alert=red). Controlled by JS changing a data attribute or class on the container. Simulated cycling every 15s.

- [ ] **Step 4: Commit**

### Task 5: Center Bottom — Command Interface + System Monitor

- [ ] **Step 1: Command input**

HTML:
- Flex row with ⚡ icon, text input (transparent bg, cyan underline), EXEC button (cyan glow, border pulse)

CSS:
- Glass panel bottom section
- Input: `caret-color: #00d4ff`, no border, no outline, cyan bottom border on focus
- EXEC button: cyan border, hover glow intensifies

- [ ] **Step 2: System monitor bars + sine wave**

4 mini progress bars (CPU, RAM, DSK, GPU) with shimmer animation.

Canvas sine wave below the bars:
```js
function drawWave(ctx, w, h, phase) {
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let x = 0; x < w; x++) {
    const y = h/2 + Math.sin((x * 0.03) + phase) * 15 + Math.sin((x * 0.07) + phase * 0.7) * 8;
    x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();
}
```

JS interval to update bar widths randomly + advance sine wave phase.

- [ ] **Step 3: Commit**

### Task 6: Right Column — Districts Panel + System Metrics

- [ ] **Step 1: Districts list**

HTML:
- DISTRICTS heading
- 10 district items with glowing bullet dots
- Active district highlighted with full glow

CSS:
- Glass panel, corner brackets
- Bullet dot: 8px circle with box-shadow glow
- Active: `.district.active` with intensified glow and cyan text
- Hover: glow transition

- [ ] **Step 2: System metrics**

5 progress bars: CPU, RAM, DSK, GPU, NET with labels and values.
Shimmer fill animation on all bars.
Values update via the same interval as center bars (synchronized).

- [ ] **Step 3: Commit**

### Task 7: Bottom Nav Bar + Polish

- [ ] **Step 1: Bottom nav bar**

HTML:
- Flex row of 6 pill buttons + status text
- "VECTOR READY" with animated waveform indicator (CSS bars)

CSS:
- Dark pills with subtle border, cyan border on hover
- Active state with stronger glow
- Waveform: 5 thin bars with staggered height animation

- [ ] **Step 2: Corner brackets on all panels**

CSS `::before` and `::after` with 2px cyan borders forming corner L-shapes:
```css
.panel::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 12px; height: 12px;
  border-top: 2px solid rgba(0,212,255,0.4);
  border-left: 2px solid rgba(0,212,255,0.4);
}
/* Repeat for each corner with different positioning */
```

- [ ] **Step 3: Hover state pass**

Every clickable element gets: `transition: all 0.3s`, hover intensifies glow/shadow.

- [ ] **Step 4: Glass morphism polish**

All panels: `background: rgba(5, 15, 30, 0.7)`, `backdrop-filter: blur(12px)`, `border: 1px solid rgba(0, 212, 255, 0.1)`

- [ ] **Step 5: Final verification**

Open in browser — verify all zones render, animations run, clock ticks, events scroll, orb breathes, rings rotate, input is interactive.

- [ ] **Step 6: Commit**
