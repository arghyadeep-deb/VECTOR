# OD-6 Channels/Comms Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicate `ChannelRegistry` registration for every confirmed same-capability channels/comms transport pair while preserving both import paths and all correctness fixes.

**Architecture:** `vectorcode/src/channels/` remains the sole implementation and registration location for concrete platform transports. Each matching `vectorcode/src/comms/` module becomes a compatibility re-export with no decorator, while genuine comms bots, daemons, sessions, inbound routing, and webhook orchestration remain unchanged. Registry discovery/package wiring is explicitly excluded.

**Tech Stack:** Python 3.12, pytest, `ChannelRegistry`, subprocess-based import isolation.

---

### Task 1: Prove the duplicate-registration defect

**Files:**
- Create: `tests/test_channels_comms_transport_reexports.py`

- [ ] **Step 1: Add a parametrized subprocess regression test**

  Cover all live overlapping keys and their class/module names. In a clean interpreter, import the channels module first, import the comms module second, and assert the exported class objects are identical and are the registry value for the key. Running each case in a subprocess prevents test collection/import order from hiding duplicate registration.

- [ ] **Step 2: Run the new test against the current tree**

  Run: `python -m pytest tests/test_channels_comms_transport_reexports.py -v`

  Expected: failures caused by `ValueError: ChannelRegistry already has an entry for '<key>'` when the second real implementation is imported.

### Task 2: Preserve comms-only fixes in canonical channels implementations

**Files:**
- Modify: `vectorcode/src/channels/gmail.py`
- Modify: `vectorcode/src/channels/reddit_channel.py`
- Modify: `vectorcode/src/channels/twilio_sms.py`
- Modify: `vectorcode/src/channels/twitch_channel.py`
- Modify: `vectorcode/src/channels/twitter_channel.py`
- Modify: `vectorcode/src/channels/viber_channel.py`
- Modify: `vectorcode/src/channels/webchat.py`
- Modify: `vectorcode/src/channels/whatsapp_baileys.py`
- Modify: `vectorcode/src/channels/zulip_channel.py`

- [ ] **Step 1: Port behavior/correctness retained only by comms**

  Preserve Twilio's complete credential validation and per-handler exception isolation; Twitch's complete credential validation; Twitter's bearer/bot-user and all-four OAuth credential validation; and the current VECTOR identity/defaults in Gmail, Reddit, Viber, WebChat, WhatsApp Baileys, and Zulip. Keep channels-only atomic token writes, IRC command-injection rejection, Twitter numeric snowflake comparison, current import paths, and newer logging behavior.

- [ ] **Step 2: Run the affected behavior regressions**

  Run: `python -m pytest tests/test_vectorcode_comms_batch_b_regressions.py tests/test_channels_audit_regressions.py tests/test_vectorcode_gmail_channel_loguru.py tests/test_vectorcode_whatsapp_baileys_loguru.py -v`

  Expected: all selected tests pass through the canonical implementations/re-export paths.

### Task 3: Replace duplicated comms transports with compatibility re-exports

**Files:**
- Modify: the 23 overlapping modules under `vectorcode/src/comms/`: `bluebubbles.py`, `discord_channel.py`, `gmail.py`, `google_chat.py`, `irc_channel.py`, `line_channel.py`, `mastodon_channel.py`, `matrix_channel.py`, `messenger_channel.py`, `nostr_channel.py`, `reddit_channel.py`, `rocketchat_channel.py`, `sendblue.py`, `signal_channel.py`, `teams.py`, `twilio_sms.py`, `twitch_channel.py`, `twitter_channel.py`, `viber_channel.py`, `webchat.py`, `whatsapp_baileys.py`, `xmpp_channel.py`, and `zulip_channel.py`

- [ ] **Step 1: Replace each implementation with a direct named re-export**

  Use the Slack daemon shim's compatibility boundary as the model, but import the channel class directly and expose it through `__all__`. Do not catch import failures and do not apply `ChannelRegistry.register` in a shim; transport import failures must remain visible and there must be exactly one registration site.

- [ ] **Step 2: Run the import/re-export regression test**

  Run: `python -m pytest tests/test_channels_comms_transport_reexports.py -v`

  Expected: 23 passed; each comms class is the exact channels class and each registry entry points to it.

- [ ] **Step 3: Run direct comms consumers and focused transport tests**

  Run: `python -m pytest tests/test_vectorcode_comms_batch_b_regressions.py tests/test_vectorcode_gmail_channel_loguru.py tests/test_vectorcode_whatsapp_baileys_loguru.py -v`

  Expected: all pass without changing the comms import paths used by callers.

### Task 4: Verify the complete requested scope

**Files:**
- Verify every modified Python file and the new regression test.

- [ ] **Step 1: Compile every touched Python file**

  Run `python -m py_compile` with the test file, all modified channels files, and all 23 comms shims as explicit arguments.

  Expected: exit code 0 and no output.

- [ ] **Step 2: Run the owner-requested focused full suite**

  Run: `python -m pytest tests/ -k "channel or comms or twitter or discord or whatsapp or signal" -v`

  Expected: report exact passed, failed, skipped, deselected, and error counts without concealing pre-existing failures.

- [ ] **Step 3: Review scope and working-tree diff**

  Confirm no `*_bot.py`, daemon/orchestration implementation, registry discovery/package wiring, unrelated code, or pre-existing owner changes were modified. Do not stage or commit.
