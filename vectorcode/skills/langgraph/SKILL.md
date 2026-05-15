<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/SKILL.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: langgraph
description: Expert in LangGraph — stateful multi-actor AI graphs. Use when wiring VECTOR's district agents into LangGraph workflows, building the governance council graph, or orchestrating multi-step agent tasks.
risk: safe
source: sickn33/antigravity-awesome-skills (Apache 2.0)
---

# LangGraph

Expert in LangGraph — the production-grade framework for building stateful, multi-actor AI applications. Covers graph construction, state management, cycles, persistence, human-in-the-loop, and ReAct agents.

## Use this skill when

- Building LangGraph workflows for VECTOR district agents
- Wiring the LLM Council into a graph (governance district)
- Creating plan-and-execute patterns for complex VECTOR tasks
- Implementing human-in-the-loop for RED-tier permission gates
- Adding checkpointers to persist agent state across loop iterations

## VECTOR + LangGraph Integration Points

- **Governance Council** → StateGraph where each council member is a node
- **RED-tier actions** → `interrupt_before` to pause for human approval
- **District pipelines** → graph replaces ad-hoc if/else routing in agents
- **Research district** → fan-out/fan-in for parallel web searches

## Core Patterns

### Basic ReAct Agent
```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

graph = StateGraph(AgentState)
graph.add_node("agent", agent_fn)
graph.add_node("tools", ToolNode(tools))
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, ["tools", END])
graph.add_edge("tools", "agent")
app = graph.compile()
```

### Human-in-the-Loop (RED actions)
```python
app = graph.compile(
    checkpointer=SqliteSaver.from_conn_string("vector_memory.db"),
    interrupt_before=["execute_action"]  # Pause at RED-tier
)
config = {"configurable": {"thread_id": "red-action-001"}}
result = app.invoke(task, config)       # Pauses before execute
app.update_state(config, {"approved": True})
result = app.invoke(None, config)       # Resume after user approves
```

### Supervisor Pattern (multi-district)
```python
# Supervisor decomposes task → delegates to district specialists
# Each specialist is a subgraph
# Results aggregated by supervisor
# Error handling at supervisor level (matches Governor pattern)
```

### Persistence
```python
from langgraph.checkpoint.sqlite import SqliteSaver
memory = SqliteSaver.from_conn_string("vector_memory.db")
app = graph.compile(checkpointer=memory)
# Resume from last checkpoint on restart — RULE 2 compliance
```

## When to Use
- Building the governance/llm_council.py district (T7)
- Creating plan-and-execute workflows in any district
- Wiring RED-tier permission gates with pause/resume
- Multi-step research or coding tasks needing state
