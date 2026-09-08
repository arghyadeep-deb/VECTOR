# Tool System

**Purpose:** All 100+ tools, capabilities  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR provides 100+ tools across filesystem, shell, browser, web, coding, databases, APIs, communication, and system control.

**Key Properties:**
- **100+ tools** — comprehensive capabilities
- **Permission-gated** — all dangerous tools go through PermissionGateway
- **MCP-compatible** — Model Context Protocol
- **Observable** — all tool calls logged

**Files:** `tools/`, `core/mcp_tools/`  
**Status:** ✅ IMPLEMENTED, production-reachable

---

## Tool Categories

### Filesystem Tools

| Tool | Purpose | Status |
|------|---------|--------|
| file_read | Read file contents | ✅ |
| file_write | Write file contents | ✅ |
| file_delete | Delete file | ✅ |
| file_move | Move/rename file | ✅ |
| file_copy | Copy file | ✅ |
| dir_list | List directory | ✅ |
| dir_create | Create directory | ✅ |

### Shell Tools

| Tool | Purpose | Status |
|------|---------|--------|
| shell_exec | Execute shell command | ✅ |
| shell_exec_async | Execute async command | ✅ |
| shell_kill | Kill process | ✅ |

### Browser Tools

| Tool | Purpose | Status |
|------|---------|--------|
| browser_navigate | Navigate to URL | ✅ |
| browser_click | Click element | ✅ |
| browser_type | Type text | ✅ |
| browser_screenshot | Take screenshot | ✅ |
| browser_scrape | Scrape page content | ✅ |
| browser_prune_dom | Prune DOM (auto-browser) | ✅ |
| browser_list_auth_profiles | List auth profiles | ✅ |

### Web Tools

| Tool | Purpose | Status |
|------|---------|--------|
| web_search | Search web | ✅ |
| web_fetch | Fetch URL | ✅ |
| web_download | Download file | ✅ |

### Coding Tools

| Tool | Purpose | Status |
|------|---------|--------|
| code_analyze | Analyze code | ✅ |
| code_format | Format code | ✅ |
| code_test | Run tests | ✅ |
| git_commit | Git commit | ✅ |
| git_push | Git push | ✅ |
| git_pull | Git pull | ✅ |

### Database Tools

| Tool | Purpose | Status |
|------|---------|--------|
| db_query | Query database | ✅ |
| db_insert | Insert record | ✅ |
| db_update | Update record | ✅ |
| db_delete | Delete record | ✅ |
| collection_list | List collections | ✅ |
| collection_query | Query collection | ✅ |
| collection_record_create | Create record | ✅ |

### Communication Tools

| Tool | Purpose | Status |
|------|---------|--------|
| send_telegram | Send Telegram message | ✅ |
| send_whatsapp | Send WhatsApp message | ✅ |
| send_discord | Send Discord message | ✅ |
| send_email | Send email | ✅ |
| send_slack | Send Slack message | ✅ |

### System Control Tools

| Tool | Purpose | Status |
|------|---------|--------|
| pc_screenshot | Take PC screenshot | ✅ |
| pc_click | Click on PC | ✅ |
| pc_type | Type on PC | ✅ |
| phone_screenshot | Take phone screenshot | ✅ |
| phone_tap | Tap on phone | ✅ |
| phone_swipe | Swipe on phone | ✅ |

### Media Tools

| Tool | Purpose | Status |
|------|---------|--------|
| image_generate | Generate image | ✅ |
| video_generate | Generate video | ✅ |
| audio_transcribe | Transcribe audio | ✅ |
| audio_synthesize | Synthesize speech | ✅ |

---

## MCP Integration

### MCP Server

**File:** `core/mcp_server.py`  
**Status:** ✅ IMPLEMENTED

```python
from mcp.server import Server

server = Server("vector")

@server.tool("file_read")
async def file_read(path: str):
    """Read file contents."""
    with open(path, 'r') as f:
        return f.read()

@server.tool("shell_exec")
async def shell_exec(command: str):
    """Execute shell command."""
    result = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await result.communicate()
    return stdout.decode()

# ... (100+ tools)
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| File operations | 1-50ms | Disk I/O |
| Shell execution | 100ms-10s | Command |
| Browser operations | 1-5s | Network |
| Database queries | 5-100ms | Query complexity |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `09_GOVERNOR_AND_PERMISSIONS.md` — Permission gates

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
