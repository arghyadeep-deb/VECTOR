# VECTOR Desktop App

Native desktop shell for VECTOR built with **Tauri 2.x** (Rust backend + system webview). Wraps the existing Vite + React + Three.js dashboard at `core/ui/dashboard/` into a real Windows / macOS / Linux executable with system tray and IPC commands.

---

## Why

VECTOR's web dashboard is great in a browser, but a native shell gives you:

- **System tray** with show/hide/logs/quit
- **Background process** that survives browser closes
- **IPC commands** (Rust ↔ frontend) for things the browser can't do — direct file system access, native notifications, OS info, shell exec
- **Backend health probe** every 30 seconds, emitted as `backend://health` event to the frontend
- **Single installable bundle**: `.msi` / `.exe` for Windows, `.dmg` for macOS, `.deb` / `.AppImage` for Linux
- **Auto-relaxed CSP** for `localhost:*` so the frontend can talk to VECTOR's FastAPI backend on `127.0.0.1:8000` without CORS gymnastics

---

## Prerequisites

1. **Rust toolchain** (stable, ≥ 1.77):
   ```powershell
   winget install Rustlang.Rust.MSVC
   ```
2. **Tauri CLI**:
   ```powershell
   cargo install tauri-cli --version "^2.0"
   ```
3. **Node.js** for the dashboard (already required by VECTOR):
   ```powershell
   winget install OpenJS.NodeJS.LTS
   ```
4. **Windows-only**: Microsoft Edge WebView2 runtime (Tauri uses it; pre-installed on Windows 11).

---

## Develop

```powershell
cd 'C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\desktop\src-tauri'
cargo tauri dev
```

This will:
1. Spawn `npm run dev` in `core/ui/dashboard/` (Vite at `http://localhost:5173`)
2. Compile the Rust shell
3. Open a native window pointed at the Vite dev server
4. Hot-reload both frontend + backend on change

> **Tip:** Make sure VECTOR's FastAPI backend is also running (`python run_vector.py api`) so the health probe finds it.

---

## Build a release bundle

```powershell
cd 'C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\desktop\src-tauri'
cargo tauri build
```

Output (per platform):

| Platform | Location |
|---|---|
| Windows | `target\release\bundle\msi\VECTOR_1.0.0_x64_en-US.msi` |
| Windows | `target\release\bundle\nsis\VECTOR_1.0.0_x64-setup.exe` |
| macOS | `target/release/bundle/dmg/VECTOR_1.0.0_aarch64.dmg` |
| Linux | `target/release/bundle/deb/vector_1.0.0_amd64.deb` |
| Linux | `target/release/bundle/appimage/vector_1.0.0_amd64.AppImage` |

The MSI / NSIS installers run with **per-user** scope by default (no admin required).

---

## Architecture

```
desktop/
└── src-tauri/
    ├── Cargo.toml           # Rust crate metadata
    ├── tauri.conf.json      # Window, CSP, bundle, tray, dev/build hooks
    ├── build.rs             # Tauri build hook
    ├── capabilities/
    │   └── default.json     # Frontend-callable command allowlist
    ├── icons/               # App icons (you need to add these — see below)
    └── src/
        └── main.rs          # Rust entry: tray, IPC, backend health probe
```

The window points at `http://localhost:5173` in dev (Vite) and `core/ui/dashboard/dist/` in production (bundled inline).

### IPC commands exposed to frontend

| Command | Returns | Purpose |
|---|---|---|
| `check_backend()` | `BackendHealth` | One-shot probe of `https://127.0.0.1:8000/health` |
| `get_backend_state()` | `string` | Last-known status: `online`/`offline`/`unknown` |
| `open_log_folder()` | `void` | Open `~/.vector/logs/` in the OS file explorer |
| `quit_app()` | `void` | Hard-quit (also via tray menu) |

### Frontend-side usage

In any React component under `core/ui/dashboard/src/`:

```ts
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

// One-shot probe
const health = await invoke<BackendHealth>('check_backend');

// Stream of 30-second probes from the Rust side
const unlisten = await listen<BackendHealth>('backend://health', (e) => {
  console.log('[VECTOR][health]', e.payload);
});
```

`@tauri-apps/api` is the only frontend dependency you need to add to `core/ui/dashboard/package.json`:

```powershell
cd '..\..\core\ui\dashboard'
npm install @tauri-apps/api
```

---

## Icons (required before first build)

Tauri needs icons in multiple sizes. Quickest path is the official CLI:

```powershell
cd 'C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\desktop\src-tauri'
# Drop a 1024x1024 PNG at ./vector-source.png first
cargo tauri icon vector-source.png
```

That generates the full set under `desktop/src-tauri/icons/`:

- `32x32.png`, `128x128.png`, `128x128@2x.png`
- `icon.ico` (Windows)
- `icon.icns` (macOS)
- `Square*Logo.png` (Microsoft Store)

You can use any 1024×1024 PNG — preferably a stylized **V** or VECTOR City emblem. Until you add one, `cargo tauri build` will fail at the icon step.

---

## Why Tauri (not Electron)?

| | Tauri 2.x | Electron |
|---|---|---|
| Bundle size | ~10 MB | ~150 MB |
| Memory at idle | ~100 MB | ~400 MB |
| Backend language | Rust | Node.js |
| Auto-update | Yes (built-in) | Plugin needed |
| System tray | Yes (built-in) | Plugin needed |
| Shipped runtime | OS webview (Edge/WebKit/WebKitGTK) | Bundled Chromium |

VECTOR is a personal AI that should run lean — Tauri matches the project's local-first ethos (small footprint, native binary, OS-integrated).

---

## What's wired

- ✅ Window with VECTOR title and dark theme default
- ✅ System tray with Show / Hide / Logs / Quit
- ✅ Backend health probe (FastAPI `/health` on `127.0.0.1:8000`) every 30s
- ✅ IPC: `check_backend`, `get_backend_state`, `open_log_folder`, `quit_app`
- ✅ CSP allows `127.0.0.1:*`, `localhost:*`, websockets, self-signed certs
- ✅ Auto-bundle for Windows / macOS / Linux
- ✅ Per-user install (no admin)

## What's not yet wired (future work)

- ⏳ Auto-update via Tauri's updater plugin
- ⏳ Deep-link `vector://` handler (open VECTOR from anywhere)
- ⏳ Global hotkey for "Hey VECTOR" (already in `core/voice/wake_word.py`, just needs a Tauri shortcut binding)
- ⏳ Rust-side LLM prefetch (bypass the Python backend for ultra-fast simple queries)
- ⏳ Native window decorations (custom title bar with VECTOR branding)
