---
layout: default
title: Vector Marketplace
description: Claude Code native agents, swarms, workers, and MCP tools for continuous software engineering
---

# Vector Marketplace

**Installable agentic workflows for Claude Code -- not just commands.**

Vector provides native Claude Code plugins for multi-agent orchestration, /loop workers, security auditing, memory-powered RAG, and test generation.

## Quick Install

```bash
# Add the marketplace
/plugin marketplace add vectorcode

# Install plugins
/plugin install vector-core@vector
/plugin install vector-swarm@vector
/plugin install vector-loop-workers@vector
```

## Plugins

| Plugin | Description | Install |
|--------|-------------|---------|
| **vector-core** | MCP server, base commands, project config | `/plugin install vector-core@vector` |
| **vector-swarm** | Teams, agents, Monitor streams, worktree isolation | `/plugin install vector-swarm@vector` |
| **vector-loop-workers** | /loop workers, CronCreate, cache-aware scheduling | `/plugin install vector-loop-workers@vector` |
| **vector-security-audit** | Security review, dependency checks, policy gates | `/plugin install vector-security-audit@vector` |
| **vector-rag-memory** | RuVector memory, HNSW search, AgentDB | `/plugin install vector-rag-memory@vector` |
| **vector-testgen** | Test gap detection, coverage analysis, TDD workflow | `/plugin install vector-testgen@vector` |
| **vector-docs** | Doc generation, drift detection, API docs | `/plugin install vector-docs@vector` |
| **vector-autopilot** | Autonomous /loop completion, learning, prediction | `/plugin install vector-autopilot@vector` |
| **vector-intelligence** | Self-learning SONA patterns, trajectory learning, routing | `/plugin install vector-intelligence@vector` |
| **vector-agentdb** | AgentDB controllers, HNSW vector search, RuVector | `/plugin install vector-agentdb@vector` |
| **vector-aidefence** | AI safety scanning, PII detection, prompt defense | `/plugin install vector-aidefence@vector` |
| **vector-browser** | Playwright browser automation, testing, scraping | `/plugin install vector-browser@vector` |
| **vector-jujutsu** | Git diff analysis, risk scoring, reviewer recs | `/plugin install vector-jujutsu@vector` |
| **vector-wasm** | Sandboxed WASM agents and gallery sharing | `/plugin install vector-wasm@vector` |
| **vector-workflows** | Workflow templates, orchestration, lifecycle | `/plugin install vector-workflows@vector` |
| **vector-daa** | Dynamic Agentic Architecture, cognitive patterns | `/plugin install vector-daa@vector` |
| **vector-ruvllm** | Local LLM inference, MicroLoRA, chat formatting | `/plugin install vector-ruvllm@vector` |
| **vector-rvf** | RVF portable memory, session persistence | `/plugin install vector-rvf@vector` |
| **vector-plugin-creator** | Scaffold, validate, publish new plugins | `/plugin install vector-plugin-creator@vector` |

## How It Works

Vector plugins extend Claude Code with:
- **Skills** -- Teach Claude Code new workflows (swarm init, /loop workers, security scans)
- **Commands** -- Slash commands for common operations (/status, /audit, /memory)
- **Agents** -- Specialized agent definitions (coder, reviewer, architect, security-auditor)
- **MCP Server** -- 314 tools for coordination, memory, neural learning, and more

## Claude Code Native Integration

Vector plugins use Claude Code's native capabilities when available:

| Feature | Plugin | Claude Code Native |
|---------|--------|--------------------|
| Periodic workers | vector-loop-workers | `/loop` + `ScheduleWakeup` |
| Live monitoring | vector-swarm | `Monitor` tool |
| Background jobs | vector-loop-workers | `CronCreate` |
| Agent isolation | vector-swarm | `isolation: "worktree"` |
| Multi-agent comms | vector-swarm | `TeamCreate` + `SendMessage` |
| Cross-session | vector-core | `PushNotification` + `RemoteTrigger` |
| Autonomous loops | vector-autopilot | `/loop` + `ScheduleWakeup` + autopilot MCP |

## Trust & Security

- All plugins are open source -- review before installing
- MCP servers run locally, no data leaves your machine
- Plugins declare required permissions in their manifest
- Pin versions for production use: `/plugin install vector-core@0.1.0@vector`
- Security scanning available via vector-security-audit

## Links

- [GitHub Repository](https://github.com/vectorcode)
- [npm Packages](https://www.npmjs.com/package/@claude-flow/cli)
- [ADR-091: Native Integration](https://github.com/vectorcode/blob/main/v3/docs/adr/ADR-091-loop-monitor-native-integration.md)
- [Issues & Support](https://github.com/vectorcode/issues)
