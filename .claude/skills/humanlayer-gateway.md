---
name: humanlayer-gateway
description: Use whenever writing tools that have side effects (file writes, git operations, API calls, database writes, network requests). Triggers on: "tool", "@hl.require_approval", "HumanLayer", any function that modifies state outside the agent
---

# HumanLayer Permission Gateway (Critical Rule #3)

## The Non-Negotiable Rule
LLM has ZERO direct access to consequential actions.
Every tool with a side effect MUST pass through HumanLayer.

## Install
```bash
pip install humanlayer
```

## Setup
```python
from humanlayer import HumanLayer, ContactChannel, SlackContactChannel

# Route approvals through District 6 (Comms / Telegram or Slack)
hl = HumanLayer(
    contact_channel=SlackContactChannel(
        channel_or_user_id="VECTOR-approvals",
        context_about_user="Arghyadeep — VECTOR owner",
    )
)
```

## Decorator Pattern (preferred)
```python
# Low-risk writes — approve once, remember
@hl.require_approval(contact_channel=hl.contact_channel)
def write_to_file(path: str, content: str) -> str:
    with open(path, "w") as f:
        f.write(content)
    return f"Written: {path}"

# High-risk — always require fresh approval
@hl.require_approval(reject_option=True)
def git_push(remote: str, branch: str) -> str:
    subprocess.run(["git", "push", remote, branch], check=True)
    return f"Pushed to {remote}/{branch}"

# Destructive — add explicit warning in description
@hl.require_approval(
    reject_option=True,
    contact_channel=hl.contact_channel,
)
def delete_file(path: str) -> str:
    """WARNING: permanently deletes file"""
    os.remove(path)
    return f"Deleted: {path}"
```

## Risk Tiers
| Tier | Examples | Approval |
|------|----------|----------|
| LOW | Read files, query LightRAG, list dirs | None needed |
| MEDIUM | Write files, git commit, API GET | @hl.require_approval |
| HIGH | git push, API POST, send message | Always approve, no auto |
| CRITICAL | Delete files, drop DB, external payment | Approve + confirm |

## NEVER auto-approve
- Any git push to main
- Any external API POST/DELETE/PUT
- Any database mutation
- Any message sent to Arghyadeep's real accounts (Telegram, email)
- Anything involving money (NEVER auto-trade, NEVER auto-pay)

## Tool Registration Pattern (for Mayor's Office)
```python
TOOLS = [
    {
        "name": "write_file",
        "fn": write_file,
        "tier": "MEDIUM",
        "requires_approval": True,
    },
    {
        "name": "query_memory",
        "fn": query_lightrag,
        "tier": "LOW",
        "requires_approval": False,
    },
]
```
