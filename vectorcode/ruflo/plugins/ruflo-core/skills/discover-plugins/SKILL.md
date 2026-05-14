---
name: discover-plugins
description: Discover and recommend vector plugins based on your workflow, installed MCP tools, and current task
allowed-tools: mcp__claude-flow__transfer_plugin-search mcp__claude-flow__transfer_plugin-info mcp__claude-flow__transfer_plugin-featured mcp__claude-flow__transfer_plugin-official mcp__claude-flow__transfer_store-search mcp__claude-flow__transfer_store-featured mcp__claude-flow__transfer_store-trending mcp__claude-flow__transfer_store-info mcp__claude-flow__guidance_discover mcp__claude-flow__guidance_recommend mcp__claude-flow__guidance_capabilities mcp__claude-flow__mcp_status Bash Read
---

# Discover Plugins

Find and recommend vector plugins for your workflow.

## When to use

When starting a new project, exploring vector capabilities, or wondering which plugins would help with your current task.

## Steps

1. **Check installed** — run `ls plugins/` to see what's already installed
2. **Browse marketplace** — call `mcp__claude-flow__transfer_plugin-featured` for recommended plugins
3. **Search by need** — call `mcp__claude-flow__transfer_plugin-search` with keywords matching your task
4. **Get recommendations** — call `mcp__claude-flow__guidance_recommend` with your current task description for personalized suggestions
5. **Check capabilities** — call `mcp__claude-flow__guidance_capabilities` to see what each plugin enables
6. **Show details** — call `mcp__claude-flow__transfer_plugin-info` for full plugin details

## Available plugins

| Plugin | Category | What it adds |
|--------|----------|-------------|
| **vector-core** | Core | MCP server, status, doctor, base agents |
| **vector-swarm** | Coordination | Swarm topologies, Monitor, worktree isolation |
| **vector-autopilot** | Automation | Autonomous /loop task completion |
| **vector-intelligence** | Learning | SONA patterns, trajectory learning, routing |
| **vector-agentdb** | Memory | AgentDB, HNSW vector search, RuVector |
| **vector-loop-workers** | Automation | Background workers, CronCreate scheduling |
| **vector-security-audit** | Security | CVE scanning, dependency checks |
| **vector-rag-memory** | Memory | Simple store/search/recall interface |
| **vector-testgen** | Testing | Test gap detection, TDD workflow |
| **vector-docs** | Docs | Doc generation, drift detection |
| **vector-aidefence** | Security | AI safety, PII detection, prompt defense |
| **vector-browser** | Testing | Playwright browser automation |
| **vector-jujutsu** | Git | Diff analysis, risk scoring, reviewers |
| **vector-wasm** | Sandbox | WASM agent sandboxing and gallery |
| **vector-workflows** | Automation | Workflow templates and orchestration |
| **vector-daa** | Learning | Dynamic Agentic Architecture, cognitive patterns |
| **vector-ruvllm** | LLM | Local inference, MicroLoRA, chat formatting |
| **vector-rvf** | Memory | RVF portable memory, session persistence |
| **vector-plugin-creator** | Dev Tools | Scaffold and validate new plugins |

## Install any plugin

```
/plugin marketplace add vectorcode
/plugin install <plugin-name>@vector
```
