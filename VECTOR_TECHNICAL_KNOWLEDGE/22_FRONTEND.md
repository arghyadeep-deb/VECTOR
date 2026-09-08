# Frontend / HUD

**Purpose:** Web dashboard, HUD interface
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR's frontend is a FastAPI-served HUD (Heads-Up Display) at `/hud/`, providing real-time monitoring and control of the autonomous loop.

**Key Properties:**
- **HUD interface** — real-time status display
- **FastAPI-served** — static files at `/hud/`
- **Command box** — send commands to VECTOR
- **Agent monitoring** — live agent status
- **Goal tracking** — active goals display

**Files:** `frontend/` (~6.3k LOC)
**Status:** ✅ IMPLEMENTED, production-reachable

---

## Architecture

### File Structure

```
frontend/
├── index.html          — main HUD page
├── css/
│   ├── style.css       — main styles
│   └── dark.css        — dark theme
├── js/
│   ├── main.js         — HUD logic
│   ├── api.js          — API client
│   ├── command-box.js  — command input
│   ├── agent-grid.js   — agent display
│   └── goal-panel.js   — goal tracking
└── assets/
    └── icons/          — SVG icons
```

---

## HUD Components

### Main Page

**File:** `frontend/index.html`
**Status:** ✅ IMPLEMENTED

```html
<!DOCTYPE html>
<html>
<head>
    <title>VECTOR HUD</title>
    <link rel="stylesheet" href="css/style.css">
    <link rel="stylesheet" href="css/dark.css">
</head>
<body>
    <header>
        <h1>VECTOR Control</h1>
        <div id="status-indicator">● Active</div>
    </header>
    
    <main>
        <section id="command-section">
            <h2>Command</h2>
            <div id="command-box"></div>
        </section>
        
        <section id="agents-section">
            <h2>Agents</h2>
            <div id="agent-grid"></div>
        </section>
        
        <section id="goals-section">
            <h2>Goals</h2>
            <div id="goal-panel"></div>
        </section>
        
        <section id="memory-section">
            <h2>Recent Memory</h2>
            <div id="memory-list"></div>
        </section>
    </main>
    
    <script src="js/main.js"></script>
    <script src="js/api.js"></script>
    <script src="js/command-box.js"></script>
    <script src="js/agent-grid.js"></script>
    <script src="js/goal-panel.js"></script>
</body>
</html>
```

### Command Box

**File:** `frontend/js/command-box.js`
**Status:** ✅ IMPLEMENTED

```javascript
class CommandBox {
    constructor() {
        this.container = document.getElementById('command-box');
        this.init();
    }
    
    init() {
        this.container.innerHTML = `
            <input type="text" id="command-input" placeholder="Send command to VECTOR...">
            <button id="command-send">Send</button>
        `;
        
        document.getElementById('command-send').onclick = () => this.send();
        document.getElementById('command-input').onkeydown = (e) => {
            if (e.key === 'Enter') this.send();
        };
    }
    
    async send() {
        const input = document.getElementById('command-input');
        const command = input.value.trim();
        
        if (!command) return;
        
        // Send to Cloudflare Worker API
        const response = await fetch('https://vector-api.workers.dev/command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command, key: VECTOR_API_KEY})
        });
        
        const result = await response.json();
        
        // Display result
        this.displayResult(command, result);
        
        input.value = '';
    }
    
    displayResult(command, result) {
        const div = document.createElement('div');
        div.className = 'command-result';
        div.innerHTML = `
            <div class="command-sent">${command}</div>
            <div class="command-response">${JSON.stringify(result, null, 2)}</div>
        `;
        this.container.appendChild(div);
    }
}
```

### Agent Grid

**File:** `frontend/js/agent-grid.js`
**Status:** ✅ IMPLEMENTED

```javascript
class AgentGrid {
    constructor() {
        this.container = document.getElementById('agent-grid');
        this.init();
    }
    
    async init() {
        await this.refresh();
        setInterval(() => this.refresh(), 5000); // refresh every 5s
    }
    
    async refresh() {
        const response = await fetch('https://vector-api.workers.dev/agents');
        const agents = await response.json();
        
        this.render(agents);
    }
    
    render(agents) {
        this.container.innerHTML = '';
        
        for (const agent of agents) {
            const card = document.createElement('div');
            card.className = 'agent-card';
            card.innerHTML = `
                <div class="agent-name">${agent.name}</div>
                <div class="agent-hp">HP: ${agent.hp}/1000</div>
                <div class="agent-status">${agent.status}</div>
                <div class="agent-district">${agent.district}</div>
            `;
            this.container.appendChild(card);
        }
    }
}
```

### Goal Panel

**File:** `frontend/js/goal-panel.js`
**Status:** ✅ IMPLEMENTED

```javascript
class GoalPanel {
    constructor() {
        this.container = document.getElementById('goal-panel');
        this.init();
    }
    
    async init() {
        await this.refresh();
        setInterval(() => this.refresh(), 10000); // refresh every 10s
    }
    
    async refresh() {
        const response = await fetch('https://vector-api.workers.dev/goals');
        const goals = await response.json();
        
        this.render(goals);
    }
    
    render(goals) {
        this.container.innerHTML = '';
        
        for (const goal of goals) {
            const card = document.createElement('div');
            card.className = 'goal-card';
            card.innerHTML = `
                <div class="goal-title">${goal.title}</div>
                <div class="goal-horizon">${goal.horizon}</div>
                <div class="goal-progress">
                    <div class="progress-bar" style="width: ${goal.progress}%"></div>
                </div>
                <div class="goal-status">${goal.status}</div>
            `;
            this.container.appendChild(card);
        }
    }
}
```

---

## FastAPI Integration

### Serving Static Files

**File:** `core/api/app.py`
**Status:** ✅ IMPLEMENTED

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Serve HUD at /hud/
app.mount("/hud", StaticFiles(directory="frontend", html=True), name="hud")
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Page load | 100-500ms | Network |
| API refresh | 50-200ms | Cloudflare latency |
| Command send | 100ms-1s | Queue processing |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `23_BACKEND_API.md` — API endpoints
- `30_DEPLOYMENT.md` — Deployment

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
