# Problem 02 - Agent Registry Returned Status Strings

## Symptom

`AgentRegistry.list_all()` returned values like `"healthy"` instead of full
agent records. The dashboard expected fields such as `agent_id`, `name`,
`district`, `generation`, `health_points`, and `is_alive`.

## Why It Matters

The VECTOR City idea depends on visible agent state. A dashboard that cannot
show HP, generation, or district is only decorative.

## Implemented Solution

Updated `AgentRegistry.list_all()` to return normalized dictionaries while
keeping compatibility with any agent object that exposes `to_dict()`.

Also added local API support:

- `core.main` bootstraps baseline agents on startup.
- `GET /agents` returns the normalized registry.
- `GET /status` now reports memory stats and agent district count.
- `POST /agent/award` now mutates real registered agents instead of returning
  `500 + points`.

## Remaining Work

- Persist living agents across process restarts.
- Add HP event history, not only current HP.
- Register real district agent classes where useful instead of baseline
  placeholder citizens.
