# VectorCode

Enterprise AI agent orchestration platform. Deploy 60+ specialized agents in coordinated swarms with self-learning, fault-tolerant consensus, vector memory, and MCP integration.

**VectorCode** is the new name for [claude-flow](https://www.npmjs.com/package/claude-flow). Both packages are fully supported.

## Install

```bash
# Quick start
npx vector@latest init --wizard

# Global install
npm install -g vector

# Add as MCP server
claude mcp add vector -- npx -y vector@latest mcp start
```

## Usage

```bash
vector init --wizard          # Initialize project
vector agent spawn -t coder   # Spawn an agent
vector swarm init             # Start a swarm
vector memory search -q "..."  # Search vector memory
vector doctor                 # System diagnostics
```

## Relationship to claude-flow

| Package | npm | CLI Command |
|---------|-----|-------------|
| `vector` | [npmjs.com/package/vector](https://www.npmjs.com/package/vector) | `vector` |
| `claude-flow` | [npmjs.com/package/claude-flow](https://www.npmjs.com/package/claude-flow) | `claude-flow` |

Both packages use `@claude-flow/cli` under the hood. Choose whichever you prefer.

## Documentation

Full documentation: [github.com/ruvnet/claude-flow](https://github.com/ruvnet/claude-flow)

## License

MIT
