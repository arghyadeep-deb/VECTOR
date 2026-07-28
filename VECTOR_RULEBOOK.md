# VECTOR — Owner's Rulebook

Your JARVIS. This is everything VECTOR can do and exactly how to make it do it.
Written for **you** (Arghyadeep), the owner — not for developers.

> **Golden rule:** VECTOR only takes real-world actions with your permission.
> It talks and thinks freely; it *acts* through a safety gate (see §7).

---

## 1. How to reach VECTOR — 3 ways

| Where | How | Best for |
|-------|-----|----------|
| **Voice (laptop)** | Say **"Hey Vector"** near the laptop | Hands-free, fastest |
| **HUD (laptop screen)** | It pops up on "Hey Vector", or open the bookmark | Seeing data, typing |
| **HUD (phone, anywhere)** | Bookmark: `http://100.115.185.102:8000/hud/?key=…` (Tailscale ON) | On the go |

- **Tailscale IP `100.115.185.102`** is permanent — works from any network.
- Your WiFi LAN IP changes when you switch networks; use the Tailscale one.
- **The laptop must be awake** for VECTOR to answer (it lives on the Legion).

---

## 2. Talking to VECTOR (voice)

1. Say **"Hey Vector"** → the HUD appears fullscreen and starts listening.
2. Speak your command clearly (1–3s delay while it transcribes).
3. VECTOR replies out loud (British male "JARVIS" voice) and shows the answer.
4. Say **"goodbye"/"that's all"** or stay silent ~45s to end the session.

**Tips for best recognition**
- Sit within arm's reach; keep mic volume near 100% (Windows → Sound → Input).
- One request at a time. If it mishears, just repeat a touch slower.
- The on-screen caption shows exactly what it heard — check there if confused.

---

## 3. Typing to VECTOR (the command bar)

At the bottom of the HUD: **"tell VECTOR…"**. Type anything, press **▶** / Enter.
- The answer is spoken and shown; if VECTOR is busy it says so (never hangs).
- Same brain as voice — anything you can say, you can type.

---

## 4. The dock (bottom icons — each is labeled)

| Button | What it does |
|--------|--------------|
| **VOICE** | Start/stop listening (also checks your mic and tells you if it's blocked) |
| **CHAT** | Open a two-way conversation panel (see history, type, get spoken replies) |
| **GOALS** | Your goals across LONG / MID / SHORT horizons with progress bars |
| **APPROVALS** | Approve / reject actions VECTOR is waiting on (the YELLOW/RED queue) |
| **PANELS** | Toggle the workspace (drag empty space to pan; double-tap to recenter) |
| **SOUND** | Mute / unmute VECTOR's voice |

Power panels (memory feed, districts/agents, council, finance, security, market…)
are reachable by typing their name in the command terminal (**Ctrl+Shift+H**).

---

## 5. What you can ask VECTOR to DO

### Control your computer & phone
- *"open spotify"* / *"open chrome"* / *"open notepad"* / *"open vs code"* — launches the app
- *"play music"* — opens Spotify
- Phone (old Oppo, USB-connected): screenshot, tap, type, launch app, post to social

### Get answers & research
- *"what are my goals"* — reads your goal state
- *"summarize what you did today"* — reflection digest
- *"research the best AI SaaS niches this week"* — fires the research district
- *"what's my KIIT attendance / schedule"* — pulls your college portal

### Plan & track
- Goals, projects, deadlines (T-7/3/1/0 alerts), daily/weekly reflection to your Brain vault
- *"remind me to…"*, *"schedule…"*

### Build & code
- *"write / fix / refactor code for X"* — coding district (review, tests, git)
- Runs your own coding stack, lean (ponytail-enforced)

### Money, health, learning (analysis, never risky moves on its own)
- Finance tracking (UPI SMS parsing), stock **analysis** (never auto-trades)
- Sleep/fatigue signals, skill-gap analysis, video/course ingestion from any URL

### Content & social (OFF until you enable it)
- Draft + queue Instagram/YouTube posts; ban-safe pacing; **won't publish** until you flip `growth.enabled` on

### Work on its own (autonomous)
- Runs a never-stopping loop: observe → think → act → reflect (2 AM daily review)
- Scans startups/news nightly, consolidates memory, self-monitors health

---

## 6. Understanding VECTOR's replies

- **Spoken + captioned** — you always see and hear the answer.
- **"On it" / "Opening X, sir"** — it understood and is acting.
- **"Waiting for your confirmation"** — a RED action needs your OK (see §7).
- **"VECTOR is busy — try again"** — the brain is mid-heavy-task; retry shortly.

---

## 7. The permission system (why it's safe)

Every action is graded. This is the JARVIS "shall I proceed, sir?" logic.

| Tier | Meaning | Examples | Behavior |
|------|---------|----------|----------|
| **GREEN** | No real-world impact | Answer, open a panel, play music control | Runs instantly |
| **YELLOW** | Reversible real action | Open an app, type, click, screenshot, launch tasks | **Owner-typed/spoken commands run immediately**; autonomous ones auto-run after a 10s veto window |
| **RED** | Irreversible / outward | Send email, post publicly, spend money, delete files | **Always asks you first** (Approvals panel / phone alert) |

You can veto anything in the **APPROVALS** panel. RED never bypasses you.

---

## 8. Remote access & always-on

- **From anywhere:** phone bookmark over Tailscale (keep Tailscale toggled on).
- **Auto-start:** VECTOR relaunches at every laptop logon (Startup shortcut).
- **Never-sleep on AC** is set, so it stays reachable while plugged in.
- **Limit:** close the lid on battery → it sleeps → VECTOR is offline till you're back.

---

## 9. Quick troubleshooting

| Problem | Fix |
|---------|-----|
| "Hey Vector" not triggering | Raise mic volume to 100%; sit closer; speak a bit louder |
| Voice can't be used in phone browser | Browsers block mic on plain HTTP — use the laptop, or ask me to set up HTTPS |
| HUD won't load / "Unauthorized" | Use the full bookmark **with** `?key=…`; make sure Tailscale is on |
| Panels blank | Fixed — they now fill instantly on open; if not, refresh the tab |
| Command seems to hang | Backend was busy; it now times out cleanly — just retry |
| VECTOR totally unreachable | Laptop asleep/off, or process died — run `scripts\vector_autostart.bat` |

---

## 10. Restart / start VECTOR manually

Double-click (or run):
```
C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\vector_autostart.bat
```
Give it ~1–2 minutes (the brain loads), then say **"Hey Vector"** or open the HUD.

---

*This rulebook reflects VECTOR as configured for you. When features change
(e.g. social posting goes live, phone control expands), this file is updated.*
