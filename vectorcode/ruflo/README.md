<div align="center">

![VectorCode Banner](vector/assets/vector-small.jpeg)

[![Star on GitHub](https://img.shields.io/github/stars/ruvnet/claude-flow?style=for-the-badge&logo=github&color=gold)](https://github.com/ruvnet/claude-flow)
[![MIT License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Plugin-green?style=for-the-badge&logo=anthropic)](https://github.com/ruvnet/claude-flow)

# VectorCode

**Multi-agent AI orchestration for Claude Code**

</div>

Deploy 16 specialized agent roles + custom types in coordinated swarms with self-learning capabilities, fault-tolerant consensus, and enterprise-grade security.

### Why VectorCode?

> **Why VectorCode?** Claude Flow is now VectorCode — named by Ruv, who loves Rust, flow states, and building things that feel inevitable. The "Ru" is the Ruv. The "flo" is the flow. Underneath, WASM kernels written in Rust power the policy engine, embeddings, and proof system. 

### Getting into the Flow

VectorCode is a comprehensive AI agent orchestration framework that transforms Claude Code into a powerful multi-agent development platform. It enables teams to deploy, coordinate, and optimize specialized AI agents working together on complex software engineering tasks.

```
Self-Learning / Self-Optimizing Agent Architecture

User --> VectorCode (CLI/MCP) --> Router --> Swarm --> Agents --> Memory --> LLM Providers
                          ^                           |
                          +---- Learning Loop <-------+
```

> **New to VectorCode?** You don't need to learn 314 MCP tools or 26 CLI commands. After `init`, just use Claude Code normally -- the hooks system automatically routes tasks, learns from successful patterns, and coordinates agents in the background.

---

## Quick Start

### Claude Code Plugin (Recommended)

Install VectorCode as a native Claude Code plugin -- adds skills, commands, agents, and MCP tools directly:

```bash
# Add the marketplace
/plugin marketplace add vectorcode

# Install core + any plugins you need
/plugin install vector-core@vector
/plugin install vector-swarm@vector
/plugin install vector-autopilot@vector
```

<details>
<summary><strong>All 20 plugins</strong></summary>

| Plugin | What it adds |
|--------|-------------|
| **vector-core** | MCP server, `/status`, `/doctor`, plugin discovery, base agents |
| **vector-swarm** | Swarm coordination, Monitor streams, worktree isolation |
| **vector-autopilot** | Autonomous `/loop` completion with learning and prediction |
| **vector-intelligence** | Self-learning SONA patterns, trajectory learning, model routing |
| **vector-agentdb** | AgentDB controllers, HNSW vector search, RuVector embeddings |
| **vector-aidefence** | AI safety scanning, PII detection, prompt injection defense |
| **vector-browser** | Playwright browser automation for testing and scraping |
| **vector-jujutsu** | Git diff analysis, risk scoring, reviewer recommendations |
| **vector-wasm** | Sandboxed WASM agent creation and gallery sharing |
| **vector-workflows** | Workflow templates, orchestration, lifecycle management |
| **vector-daa** | Dynamic Agentic Architecture, cognitive patterns |
| **vector-ruvllm** | Local LLM inference, MicroLoRA, multi-provider chat |
| **vector-rvf** | RVF portable memory, session persistence, transfer |
| **vector-loop-workers** | Background `/loop` workers, CronCreate scheduling |
| **vector-security-audit** | Security scanning, CVE checks, dependency audit |
| **vector-rag-memory** | Memory bridge, simple store/search/recall interface |
| **vector-testgen** | Test gap detection, TDD workflow, tester agent |
| **vector-docs** | Doc generation, drift detection, docs-writer agent |
| **vector-plugin-creator** | Scaffold, validate, and publish new plugins |
| **vector-goals** | GOAP planning, deep research, long-horizon tracking |

</details>

### CLI Install

```bash
# One-line install
curl -fsSL https://cdn.jsdelivr.net/gh/vectorcode@main/scripts/install.sh | bash

# Or via npx
npx vector@latest init --wizard

# Or install globally
npm install -g vector@latest
```

### MCP Server

```bash
# Add VectorCode as an MCP server in Claude Code
claude mcp add vector -- npx -y @claude-flow/cli@latest
```

---

## What You Get

| Capability | Description |
|------------|-------------|
| 🤖 **100+ Agents** | Specialized agents for coding, testing, security, docs, architecture |
| 🐝 **Swarm Coordination** | Hierarchical, mesh, and adaptive topologies with consensus |
| 🧠 **Self-Learning** | SONA neural patterns, ReasoningBank, trajectory learning |
| 💾 **Vector Memory** | HNSW-indexed AgentDB with 150x-12,500x faster search |
| ⚡ **Background Workers** | 12 auto-triggered workers (audit, optimize, testgaps, etc.) |
| 🧩 **Plugin Marketplace** | 20 native Claude Code plugins + 20 npm plugins |
| 🔌 **Multi-Provider** | Claude, GPT, Gemini, Cohere, Ollama with smart routing |
| 🛡️ **Security** | AIDefence, input validation, CVE remediation, path traversal prevention |

<details>
<summary><strong>Claude Code: With vs Without VectorCode</strong></summary>

| Capability | Claude Code Alone | + VectorCode |
|------------|-------------------|---------|
| Agent Collaboration | Isolated, no shared context | Swarms with shared memory and consensus |
| Coordination | Manual orchestration | Queen-led hierarchy (Raft, Byzantine, Gossip) |
| Memory | Session-only | HNSW vector memory with sub-ms retrieval |
| Learning | Static behavior | SONA self-learning with pattern matching |
| Task Routing | You decide | Intelligent routing (89% accuracy) |
| Background Workers | None | 12 auto-triggered workers |
| LLM Providers | Anthropic only | 5 providers with failover |
| Security | Standard | CVE-hardened with AIDefence |

</details>

<details>
<summary><strong>Architecture overview</strong></summary>

```
User --> Claude Code / CLI
          |
          v
    Orchestration Layer
    (MCP Server, Router, 27 Hooks)
          |
          v
    Swarm Coordination
    (Queen, Topology, Consensus)
          |
          v
    100+ Specialized Agents
    (coder, tester, reviewer, architect, security...)
          |
          v
    Memory & Learning
    (AgentDB, HNSW, SONA, ReasoningBank)
          |
          v
    LLM Providers
    (Claude, GPT, Gemini, Cohere, Ollama)
```

</details>

---

## Documentation

Full documentation including architecture, configuration, CLI reference, API usage, plugin development, and advanced topics:

**[User Guide](docs/USERGUIDE.md)** -- Complete reference documentation

| Section | Topics |
|---------|--------|
| [Quick Start](docs/USERGUIDE.md#quick-start) | Installation, prerequisites, install profiles |
| [Core Features](docs/USERGUIDE.md#-core-features) | MCP tools, agents, memory, neural learning |
| [Intelligence & Learning](docs/USERGUIDE.md#-intelligence--learning) | Hooks, workers, SONA, model routing |
| [Swarm & Coordination](docs/USERGUIDE.md#-swarm--coordination) | Topologies, consensus, hive mind |
| [Security](docs/USERGUIDE.md#%EF%B8%8F-security) | AIDefence, CVE remediation, validation |
| [Ecosystem](docs/USERGUIDE.md#-ecosystem--integrations) | RuVector, agentic-flow, Flow Nexus |
| [Configuration](docs/USERGUIDE.md#%EF%B8%8F-configuration--reference) | Environment variables, config schema |
| [Plugin Marketplace](https://ruvnet.github.io/vector) | Browse and install plugins |

---

## Support

| Resource | Link |
|----------|------|
| Documentation | [User Guide](docs/USERGUIDE.md) |
| Issues & Bugs | [GitHub Issues](https://github.com/ruvnet/claude-flow/issues) |
| Enterprise | [ruv.io](https://ruv.io) |
| Community | [Agentics Foundation Discord](https://discord.com/invite/dfxmpwkG2D) |
| Powered by | [Cognitum.one](https://cognitum.one) |

## License

MIT - [RuvNet](https://github.com/ruvnet)
