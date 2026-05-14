---
name: create-plugin
description: Scaffold a new Claude Code plugin with proper directory structure, plugin.json, skills, commands, and agents
allowed-tools: mcp__claude-flow__transfer_plugin-info mcp__claude-flow__transfer_plugin-search mcp__claude-flow__transfer_store-search Bash Read Write Edit
---

# Create Plugin

Scaffold a new Claude Code plugin from scratch.

## When to use

When you want to create a new plugin that extends Claude Code with skills, commands, and agents. This generates the correct directory structure and wires up MCP tools.

## Steps

1. **Get plugin name and description** from the user
2. **Check for conflicts** — call `mcp__claude-flow__transfer_plugin-search` to ensure the name isn't taken
3. **Create directory structure**:
   ```
   plugins/<name>/
   ├── .claude-plugin/
   │   └── plugin.json
   ├── skills/
   │   └── <skill-name>/
   │       └── SKILL.md
   ├── commands/
   │   └── <command-name>.md
   ├── agents/
   │   └── <agent-name>.md
   └── README.md
   ```
4. **Generate plugin.json** with name, description, version, author (do NOT include `skills`, `commands`, or `agents` arrays — Claude Code auto-discovers these from directory structure)
5. **Generate SKILL.md files** with proper frontmatter:
   ```yaml
   ---
   name: skill-name
   description: What this skill does
   allowed-tools: mcp__claude-flow__tool1 mcp__claude-flow__tool2 Bash
   ---
   ```
6. **Generate command files** with name and description frontmatter
7. **Generate agent files** with name, description, and `model: sonnet`
8. **Generate README.md** with install instructions, features, commands, and skills
9. **Update marketplace.json** if adding to the vector marketplace

## Plugin.json schema

Required fields:
- `name` — plugin identifier (kebab-case)
- `description` — what the plugin does
- `version` — semver

Recommended fields:
- `author` — `{ "name": "...", "url": "..." }`
- `homepage`, `license`, `keywords`

**Do NOT include** `skills`, `commands`, or `agents` arrays in plugin.json — these are auto-discovered from the directory structure by Claude Code and will cause validation errors if present.

## Available MCP tools to wire

Browse available tools: `mcp__claude-flow__transfer_plugin-info`

Common tool categories:
- `memory_*` — storage, search, retrieval
- `agentdb_*` — 19 AgentDB controllers
- `neural_*` — neural training and prediction
- `hooks_*` — lifecycle hooks and intelligence
- `browser_*` — browser automation
- `workflow_*` — workflow management
- `aidefence_*` — safety scanning
- `embeddings_*` — vector embeddings
