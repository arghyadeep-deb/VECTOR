# Behavioral Nudging Engine — Implementation Plan

**Goal:** Monitor activity patterns, detect work states, surface proactive nudges.
**Architecture:** Python cron loop → rule engine → Ollama nudge text → API endpoint → dashboard toast + voice.

---

### Task 1: NudgeEngine backend

**File:** Create `core/loop/nudge_engine.py`

```python
"""NudgeEngine — monitors activity patterns and generates proactive nudges."""

import asyncio
import datetime
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class NudgeEngine:
    def __init__(self):
        self._latest: dict | None = None
        self._session_start = time.time()
        self._last_build_errors: list[float] = []
        self._last_idle_time = 0.0
        self._active_30m_count = 0
        self._check_interval = 30  # seconds

    @property
    def latest(self) -> dict | None:
        return self._latest

    def dismiss(self):
        self._latest = None

    async def tick(self):
        signals = self._collect_signals()
        rule = self._match_rule(signals)
        if rule:
            text = await self._generate_nudge(rule, signals)
            self._latest = {
                "text": text,
                "rule": rule["name"],
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "signals": signals,
            }
            logger.info(f"[VECTOR][nudge] {rule['name']}: {text}")

    def _collect_signals(self) -> dict:
        signals = {
            "uptime_minutes": (time.time() - self._session_start) / 60,
            "git_commits_1h": self._count_git_commits(60),
            "git_commits_5m": self._count_git_commits(5),
            "idle_seconds": 0,
            "errors_5m": 0,
            "active_window": "",
        }
        # Idle time via psutil if available
        try:
            import psutil
            # Cross-platform idle detection via CPU usage
            cpu = psutil.cpu_percent(interval=0.5)
            if cpu < 5:
                signals["idle_seconds"] = self._last_idle_time + self._check_interval
            else:
                signals["idle_seconds"] = 0
                self._last_idle_time = 0
        except Exception:
            signals["idle_seconds"] = 0
        return signals

    def _count_git_commits(self, minutes: int) -> int:
        try:
            since = f"{minutes} minutes ago"
            r = subprocess.run(
                ["git", "log", f"--since={since}", "--oneline"],
                capture_output=True, text=True, timeout=5,
                cwd=Path(__file__).parent.parent.parent,
            )
            return len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
        except Exception:
            return 0

    def _match_rule(self, signals: dict) -> dict | None:
        rules = [
            {
                "name": "deep_work",
                "condition": (
                    signals["uptime_minutes"] >= 45
                    and signals["idle_seconds"] < 30
                    and signals["git_commits_5m"] >= 1
                ),
                "template": "deep_work",
            },
            {
                "name": "long_session",
                "condition": signals["uptime_minutes"] >= 120 and signals["idle_seconds"] < 30,
                "template": "long_session",
            },
            {
                "name": "idle",
                "condition": signals["idle_seconds"] >= 600,
                "template": "idle",
            },
        ]
        for rule in rules:
            if rule["condition"]:
                return rule
        return None

    async def _generate_nudge(self, rule: dict, signals: dict) -> str:
        import httpx
        prompts = {
            "deep_work": (
                "Generate a one-sentence encouraging nudge for a developer "
                "who has been coding for 45+ minutes with recent git commits. "
                "Acknowledge their focus briefly. No emoji."
            ),
            "long_session": (
                "Generate a one-sentence gentle nudge suggesting a short break "
                "for a developer who has been working for 2+ hours. No emoji."
            ),
            "idle": (
                "Generate a one-sentence helpful nudge for a developer who has "
                "been idle for 10+ minutes. Ask if they need help researching "
                "something. No emoji."
            ),
        }
        prompt = prompts.get(rule["template"], "")
        if not prompt:
            return "You seem to be in a good rhythm. Keep going."

        try:
            ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{ollama_host}/api/generate",
                    json={"model": "llama3.2:latest", "prompt": prompt, "stream": False},
                )
                if r.status_code == 200:
                    return r.json().get("response", "").strip()
        except Exception as e:
            logger.warning(f"[VECTOR][nudge] LLM failed: {e}")

        return self._fallback_nudge(rule["template"])

    def _fallback_nudge(self, template: str) -> str:
        fallbacks = {
            "deep_work": "You've been in deep focus for 45 minutes. The work is solid.",
            "long_session": "You've been at this for 2 hours. A quick break will help.",
            "idle": "You seem idle. Want me to run some diagnostics?",
        }
        return fallbacks.get(template, "Stay sharp, sir.")


nudge_engine = NudgeEngine()
```

- [ ] Write file
- [ ] Run: `python -c "from core.loop.nudge_engine import nudge_engine; print('OK')"` → expect OK

---

### Task 2: Nudge API router

**File:** Create `core/api/routers/nudge.py`

```python
"""Nudge router — /nudge endpoints."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/nudge", tags=["nudge"])


@router.get("/latest")
async def nudge_latest():
    from core.loop.nudge_engine import nudge_engine
    n = nudge_engine.latest
    if n:
        return n
    return {"text": None, "rule": None, "timestamp": None}


@router.post("/dismiss")
async def nudge_dismiss():
    from core.loop.nudge_engine import nudge_engine
    nudge_engine.dismiss()
    return {"status": "dismissed"}
```

- [ ] Write file
- [ ] Register in `core/api/app.py` (add `nudge` to imports + `app.include_router(nudge.router)`)
- [ ] Run: `python -c "from core.api.routers.nudge import router; print('OK')"` → expect OK

---

### Task 3: NudgeToast frontend component

**File:** Create `core/ui/dashboard/src/components/NudgeToast.tsx`

```tsx
import { useState, useEffect, useCallback } from 'react'

interface NudgeData {
  text: string | null
  rule: string | null
  timestamp: string | null
}

const POLL_INTERVAL = 15000
const SPEAK_INTERVAL = 60000

export default function NudgeToast() {
  const [nudge, setNudge] = useState<NudgeData | null>(null)
  const [visible, setVisible] = useState(false)
  const [lastSpoken, setLastSpoken] = useState(0)

  const fetchNudge = useCallback(async () => {
    try {
      const r = await fetch('/nudge/latest')
      const data: NudgeData = await r.json()
      if (data.text) {
        setNudge(data)
        setVisible(true)
        const now = Date.now()
        if (now - lastSpoken > SPEAK_INTERVAL) {
          setLastSpoken(now)
          try {
            const u = new URL('/voice/speak', window.location.origin)
            await fetch(u.toString(), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ text: data.text }),
            })
          } catch { /* silent */ }
        }
      }
    } catch { /* silent */ }
  }, [lastSpoken])

  useEffect(() => {
    const id = setInterval(fetchNudge, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [fetchNudge])

  const dismiss = useCallback(async () => {
    try {
      await fetch('/nudge/dismiss', { method: 'POST' })
    } catch { /* silent */ }
    setVisible(false)
  }, [])

  if (!visible || !nudge) return null

  return (
    <div style={{
      position: 'fixed', bottom: 60, left: '50%', transform: 'translateX(-50%)',
      background: 'rgba(5,13,26,0.95)', backdropFilter: 'blur(16px)',
      border: '1px solid rgba(0,212,255,0.2)',
      boxShadow: '0 0 30px rgba(0,212,255,0.08)',
      padding: '12px 20px', borderRadius: 4, zIndex: 9999,
      display: 'flex', alignItems: 'center', gap: 14,
      fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#a8d8f0',
      animation: 'fadeIn 0.3s ease',
    }}>
      <span style={{ color: '#4FC3F7', fontFamily: "'Orbitron', sans-serif", fontSize: 8, letterSpacing: '0.1em' }}>
        NUDGE
      </span>
      <span>{nudge.text}</span>
      <button
        onClick={dismiss}
        style={{
          background: 'transparent', border: '1px solid rgba(0,212,255,0.15)',
          color: '#4FC3F7', cursor: 'pointer', padding: '4px 10px',
          fontFamily: "'Orbitron', sans-serif", fontSize: 8,
        }}
      >
        ✕
      </button>
    </div>
  )
}
```

- [ ] Write file

---

### Task 4: Wire NudgeToast into App.tsx

**File:** Modify `core/ui/dashboard/src/App.tsx`

- [ ] Add `import NudgeToast from './components/NudgeToast'`
- [ ] Add `<NudgeToast />` near end of component tree (above closing fragments)

---

### Task 5: Add speak endpoint for nudge TTS

**File:** Modify `core/api/routers/voice.py` or new small endpoint

Add `POST /voice/speak` — accepts `{"text": "..."}` → runs Kokoro TTS (no STT/LLM).

```python
@router.post("/speak")
async def voice_speak(body: dict):
    text = body.get("text", "")
    if not text:
        return {"status": "no_text"}
    try:
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        import asyncio
        await asyncio.to_thread(tts.speak, text)
        return {"status": "spoken"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

- [ ] Add to `core/api/routers/voice.py`
- [ ] Verify: `python -c "from core.api.routers.voice import router; print('OK')"`

---

### Task 6: Build and verify

- [ ] Run: `cd core/ui/dashboard && npx vite build` → expect PASS
- [ ] Verify no import errors in nudge engine: `python -c "from core.loop.nudge_engine import nudge_engine; print(nudge_engine.latest)"` → expect None
