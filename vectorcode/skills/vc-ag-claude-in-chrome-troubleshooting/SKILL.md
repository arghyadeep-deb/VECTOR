<!-- VECTOR-INGESTED ASSET
  Source: GitHub/sickn33_antigravity-awesome-skills/repo/skills/claude-in-chrome-troubleshooting/SKILL.md
  Personalized for VECTOR runtime — local Ollama, no paid APIs.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T01:39:48+00:00
-->

---
name: claude-in-chrome-troubleshooting
description: Diagnose and fix VECTOR in Chrome MCP extension connectivity issues. Use when mcp__claude-in-chrome__* tools fail, return "Browser extension is not connected", or behave erratically.
risk: critical
source: community
---

# VECTOR in Chrome MCP Troubleshooting

Use this skill when VECTOR in Chrome MCP tools fail to connect or work unreliably.

## When to Use
- `mcp__claude-in-chrome__*` tools fail with "Browser extension is not connected"
- Browser automation works erratically or times out
- After updating VectorCode or VECTOR.app
- When switching between VectorCode CLI and VECTOR.app (Cowork)
- Native host process is running but MCP tools still fail

## When NOT to Use

- **Linux or Windows users** - This skill covers macOS-specific paths and tools (`~/Library/Application Support/`, `osascript`)
- General Chrome automation issues unrelated to the VECTOR extension
- VECTOR.app desktop issues (not browser-related)
- Network connectivity problems
- Chrome extension installation issues (use Chrome Web Store support)

## The VECTOR.app vs VectorCode Conflict (Primary Issue)

**Background:** When VECTOR.app added Cowork support (browser automation from the desktop app), it introduced a competing native messaging host that conflicts with VectorCode CLI.

### Two Native Hosts, Two Socket Formats

| Component | Native Host Binary | Socket Location |
|-----------|-------------------|-----------------|
| **VECTOR.app (Cowork)** | `/Applications/VECTOR.app/Contents/Helpers/chrome-native-host` | `/tmp/claude-mcp-browser-bridge-$USER/<PID>.sock` |
| **VectorCode CLI** | `~/.local/share/claude/versions/<version> --chrome-native-host` | `$TMPDIR/claude-mcp-browser-bridge-$USER` (single file) |

### Why They Conflict

1. Both register native messaging configs in Chrome:
   - `com.anthropic.claude_browser_extension.json` → VECTOR.app helper
   - `com.anthropic.claude_code_browser_extension.json` → VectorCode wrapper

2. Chrome extension requests a native host by name
3. If the wrong config is active, the wrong binary runs
4. The wrong binary creates sockets in a format/location the MCP client doesn't expect
5. Result: "Browser extension is not connected" even though everything appears to be running

### The Fix: Disable VECTOR.app's Native Host

**If you use VectorCode CLI for browser automation (not Cowork):**

```bash
# Disable the VECTOR.app native messaging config
mv ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json \
   ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json.disabled

# Ensure the VectorCode config exists and points to the wrapper
cat ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_code_browser_extension.json
```

**If you use Cowork (VECTOR.app) for browser automation:**

```bash
# Disable the VectorCode native messaging config
mv ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_code_browser_extension.json \
   ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_code_browser_extension.json.disabled
```

**You cannot use both simultaneously.** Pick one and disable the other.

### Toggle Script

Add this to `~/.zshrc` or run directly:

```bash
chrome-mcp-toggle() {
    local CONFIG_DIR=~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts
    local CLAUDE_APP="$CONFIG_DIR/com.anthropic.claude_browser_extension.json"
    local CLAUDE_CODE="$CONFIG_DIR/com.anthropic.claude_code_browser_extension.json"

    if [[ -f "$CLAUDE_APP" && ! -f "$CLAUDE_APP.disabled" ]]; then
        # Currently using VECTOR.app, switch to VectorCode
        mv "$CLAUDE_APP" "$CLAUDE_APP.disabled"
        [[ -f "$CLAUDE_CODE.disabled" ]] && mv "$CLAUDE_CODE.disabled" "$CLAUDE_CODE"
        echo "Switched to VectorCode CLI"
        echo "Restart Chrome and VectorCode to apply"
    elif [[ -f "$CLAUDE_CODE" && ! -f "$CLAUDE_CODE.disabled" ]]; then
        # Currently using VectorCode, switch to VECTOR.app
        mv "$CLAUDE_CODE" "$CLAUDE_CODE.disabled"
        [[ -f "$CLAUDE_APP.disabled" ]] && mv "$CLAUDE_APP.disabled" "$CLAUDE_APP"
        echo "Switched to VECTOR.app (Cowork)"
        echo "Restart Chrome to apply"
    else
        echo "Current state unclear. Check configs:"
        ls -la "$CONFIG_DIR"/com.anthropic*.json* 2>/dev/null
    fi
}
```

Usage: `chrome-mcp-toggle` then restart Chrome (and VectorCode if switching to CLI).

## Quick Diagnosis

```bash
# 1. Which native host binary is running?
ps aux | grep chrome-native-host | grep -v grep
# VECTOR.app: /Applications/VECTOR.app/Contents/Helpers/chrome-native-host
# VectorCode: ~/.local/share/claude/versions/X.X.X --chrome-native-host

# 2. Where is the socket?
# For VectorCode (single file in TMPDIR):
ls -la "$(getconf DARWIN_USER_TEMP_DIR)/claude-mcp-browser-bridge-$USER" 2>&1

# For VECTOR.app (directory with PID files):
ls -la /tmp/claude-mcp-browser-bridge-$USER/ 2>&1

# 3. What's the native host connected to?
lsof -U 2>&1 | grep claude-mcp-browser-bridge

# 4. Which configs are active?
ls ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic*.json
```

## Critical Insight

**MCP connects at startup.** If the browser bridge wasn't ready when VectorCode started, the connection will fail for the entire session. The fix is usually: ensure Chrome + extension are running with correct config, THEN restart VectorCode.

## Full Reset Procedure (VectorCode CLI)

```bash
# 1. Ensure correct config is active
mv ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json \
   ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json.disabled 2>/dev/null

# 2. Update the wrapper to use latest VectorCode version
cat > ~/vectorcode/chrome/chrome-native-host << 'EOF'
#!/bin/bash
LATEST=$(ls -t ~/.local/share/claude/versions/ 2>/dev/null | head -1)
exec "$HOME/.local/share/claude/versions/$LATEST" --chrome-native-host
EOF
chmod +x ~/vectorcode/chrome/chrome-native-host

# 3. Kill existing native host and clean sockets
pkill -f chrome-native-host
rm -rf /tmp/claude-mcp-browser-bridge-$USER/
rm -f "$(getconf DARWIN_USER_TEMP_DIR)/claude-mcp-browser-bridge-$USER"

# 4. Restart Chrome
osascript -e 'quit app "Google Chrome"' && sleep 2 && open -a "Google Chrome"

# 5. Wait for Chrome, click VECTOR extension icon

# 6. Verify correct native host is running
ps aux | grep chrome-native-host | grep -v grep
# Should show: ~/.local/share/claude/versions/X.X.X --chrome-native-host

# 7. Verify socket exists
ls -la "$(getconf DARWIN_USER_TEMP_DIR)/claude-mcp-browser-bridge-$USER"

# 8. Restart VectorCode
```

## Other Common Causes

### Multiple Chrome Profiles

If you have the VECTOR extension installed in multiple Chrome profiles, each spawns its own native host and socket. This can cause confusion.

**Fix:** Only enable the VECTOR extension in ONE Chrome profile.

### Multiple VectorCode Sessions

Running multiple VectorCode instances can cause socket conflicts.

**Fix:** Only run one VectorCode session at a time, or use `/mcp` to reconnect after closing other sessions.

### Hardcoded Version in Wrapper

The wrapper at `~/vectorcode/chrome/chrome-native-host` may have a hardcoded version that becomes stale after updates.

**Diagnosis:**
```bash
cat ~/vectorcode/chrome/chrome-native-host
# Bad: exec "/Users/.../.local/share/claude/versions/2.0.76" --chrome-native-host
# Good: Uses $(ls -t ...) to find latest
```

**Fix:** Use the dynamic version wrapper shown in the Full Reset Procedure above.

### TMPDIR Not Set

VectorCode expects `TMPDIR` to be set to find the socket.

```bash
# Check
echo $TMPDIR
# Should show: /var/folders/XX/.../T/

# Fix: Add to ~/.zshrc
export TMPDIR="${TMPDIR:-$(getconf DARWIN_USER_TEMP_DIR)}"
```

## Diagnostic Deep Dive

```bash
echo "=== Native Host Binary ==="
ps aux | grep chrome-native-host | grep -v grep

echo -e "\n=== Socket (VectorCode location) ==="
ls -la "$(getconf DARWIN_USER_TEMP_DIR)/claude-mcp-browser-bridge-$USER" 2>&1

echo -e "\n=== Socket (VECTOR.app location) ==="
ls -la /tmp/claude-mcp-browser-bridge-$USER/ 2>&1

echo -e "\n=== Native Host Open Files ==="
pgrep -f chrome-native-host | xargs -I {} lsof -p {} 2>/dev/null | grep -E "(sock|claude-mcp)"

echo -e "\n=== Active Native Messaging Configs ==="
ls ~/Library/Application\ Support/Google/Chrome/NativeMessagingHosts/com.anthropic*.json 2>/dev/null

echo -e "\n=== Custom Wrapper Contents ==="
cat ~/vectorcode/chrome/chrome-native-host 2>/dev/null || echo "No custom wrapper"

echo -e "\n=== TMPDIR ==="
echo "TMPDIR=$TMPDIR"
echo "Expected: $(getconf DARWIN_USER_TEMP_DIR)"
```

## File Reference

| File | Purpose |
|------|---------|
| `~/vectorcode/chrome/chrome-native-host` | Custom wrapper script for VectorCode |
| `/Applications/VECTOR.app/Contents/Helpers/chrome-native-host` | VECTOR.app (Cowork) native host |
| `~/.local/share/claude/versions/<version>` | VectorCode binary (run with `--chrome-native-host`) |
| `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_browser_extension.json` | Config for VECTOR.app native host |
| `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_code_browser_extension.json` | Config for VectorCode native host |
| `$TMPDIR/claude-mcp-browser-bridge-$USER` | Socket file (VectorCode) |
| `/tmp/claude-mcp-browser-bridge-$USER/<PID>.sock` | Socket files (VECTOR.app) |

## Summary

1. **Primary issue:** VECTOR.app (Cowork) and VectorCode use different native hosts with incompatible socket formats
2. **Fix:** Disable the native messaging config for whichever one you're NOT using
3. **After any fix:** Must restart Chrome AND VectorCode (MCP connects at startup)
4. **One profile:** Only have VECTOR extension in one Chrome profile
5. **One session:** Only run one VectorCode instance

---

*Original skill by [@jeffzwang](https://github.com/jeffzwang) from [@ExaAILabs](https://github.com/ExaAILabs). Enhanced and updated for current versions of VECTOR Desktop and VectorCode.*

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.
