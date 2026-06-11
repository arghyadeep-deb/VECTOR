# Task 14 — Phone ambient node (Termux)

- **Depends on:** Task 12
- **Who:** OWNER (old Android in hand)
- **Effort:** ~30 min

## Objective

The old Android runs `phone_node/ambient_server.py` under Termux: ambient
sensing + notifications bridge, heartbeating to the cloud brain.

## Implementation

On the phone (Termux):
```
pkg install python git
bash phone_node/setup.sh
```
Configure the cloud brain URL from Task 12.

## Tests

Phone's `/status` reachable on LAN; heartbeat rows appear server-side.

## Demo

Loop log on the Legion shows phone ambient events arriving.

## Acceptance

- [ ] ambient_server runs and survives Termux restart (termux-services)
- [ ] Heartbeats reach cloud brain
- [ ] A notification on the phone lands in episodic memory
