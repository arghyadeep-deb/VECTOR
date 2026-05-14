# VectorCode TUI

`@vectorcode/tui` — React/Ink-based terminal interface for VectorCode.

## Architecture

```
┌──────────────────────────────────────────────┐
│ TopBar:  ⟨▶⟩ VectorCode · model · mode · ●    │  status line
├──────────────────────────────────┬───────────┤
│ ChatPane                         │ ToolPane  │
│   user messages                  │  ● tool   │  optional
│   assistant streaming            │  ✓ tool   │
│   tool results                   │  ✗ tool   │
│                                  │           │
├──────────────────────────────────┴───────────┤
│ InputBar:  > _                               │  user input
│   /slash command suggestions above           │
├──────────────────────────────────────────────┤
│ StatusLine: iter 12/90 [█████░░] · hints     │
└──────────────────────────────────────────────┘
```

## Components

| File | Role |
|------|------|
| `src/index.tsx` | CLI entry — argv parsing, render |
| `src/App.tsx` | Top-level orchestrator, state, dispatch |
| `src/gatewayClient.ts` | HTTP + SSE client to VectorCode gateway |
| `src/types.ts` | Shared types (ChatMessage, ToolEvent, SessionStatus, GatewayEvent) |
| `src/slashCommands.ts` | Slash command registry for autocomplete |
| `src/ui/theme.ts` | Colors + glyphs + layout constants |
| `src/ui/Banner.tsx` | Welcome banner |
| `src/ui/TopBar.tsx` | Persistent status header |
| `src/ui/ChatPane.tsx` | Conversation view with streaming |
| `src/ui/ToolPane.tsx` | Right-side tool execution timeline |
| `src/ui/InputBar.tsx` | Text input + slash autocomplete |
| `src/ui/StatusLine.tsx` | Bottom thin status (iterations, hints) |

## Install

```bash
cd vectorcode/packages/cli
npm install
```

## Run

### Dev mode (no compile)

```bash
npm run dev
```

### Production

```bash
npm run build
npm start

# Or once built and linked:
vector-tui --gateway http://127.0.0.1:8123 --model anthropic/claude-sonnet-4-5
```

## Pre-flight

The TUI talks to VectorCode's gateway. Start it first:

```bash
vector gateway start --port 8123
```

Then in another terminal:

```bash
vector-tui
```

## Hotkeys

| Key | Action |
|-----|--------|
| `Tab` | Toggle tool pane |
| `Ctrl+C` | Cancel current run |
| `Esc` | Clear input |
| `/help` | Show all slash commands |
| `/quit` | Exit |
| `↑` / `↓` | History navigation (planned) |

## Slash commands

All standard VectorCode slash commands work: `/model`, `/mode`, `/sparc`, `/spawn`,
`/diff`, `/commit`, `/compact`, `/cost`, `/save`, `/restore`, `/skills`, `/tools`,
`/notify`, `/comms`, `/search`, `/fetch`, `/usage`, `/persona`, `/help`,
`/status`, `/clear`, `/reset`, `/quit`.

See `src/slashCommands.ts` for the full registry.

## Theming

Edit `src/ui/theme.ts` to change colors / glyphs. The default theme matches the
VectorCode Python CLI banner aesthetic.

## Bundling to a single binary (optional)

```bash
# With bun
bun build src/index.tsx --compile --outfile=vector-tui

# With pkg
npx pkg dist/index.js --targets node20-win-x64,node20-linux-x64,node20-macos-x64
```
