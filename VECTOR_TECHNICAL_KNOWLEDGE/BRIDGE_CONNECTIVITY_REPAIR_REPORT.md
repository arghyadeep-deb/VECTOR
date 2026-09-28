# Bridge Connectivity Repair Report

Date: 2026-09-22

## Scope

This mission was limited to the existing VECTOR Claude/Codex development bridge under `tools/vector_dev_orchestrator/**`.

No VECTOR production code was modified. VECTOR was not started. No tests outside bridge diagnostics were run.

## Initial Failure

The prior connectivity diagnostic failed in the Codex to Claude direction:

- Codex invoked `tools/vector_dev_orchestrator/claude_adapter.py`
- `ClaudeAdapter.run_read_only(...)` requested provider `claude`, model `haiku`
- Claude CLI produced no stdout and no stderr
- The invocation hung for about 90 seconds and was manually interrupted
- Reverse Claude to Codex testing was not run

## Baseline Repository State

Initial HEAD:

```text
d3994e586de5689f4b5d6f1c209b97d65d0ca16d
```

Initial branch:

```text
production-hardening-complete
```

Initial `git status --short` contained pre-existing dirty/runtime artifacts, including:

```text
 M VECTOR_TECHNICAL_KNOWLEDGE/OWNER_ROUTING_CLOSURE_REPORT.md
 M data/council_log.jsonl
 M data/models/neural_policy.meta.json
 M data/models/neural_policy.pt
?? .claude/settings.local.backup-2026-09-14.json
?? tools/vector_dev_orchestrator/
```

## Adapter Trace

Inspected file:

```text
tools/vector_dev_orchestrator/claude_adapter.py
```

`ClaudeAdapter.run_read_only()` builds a command through `build_read_only_command()`.

Observed command shape:

```text
claude -p <prompt> --model <model> --effort <effort> --permission-mode plan --output-format json --safe-mode --setting-sources local --tools Read
```

Adapter behavior:

- executable: resolved by `shutil.which("claude")`
- prompt transport: command-line argument after `-p`
- stdin behavior: no stdin input is supplied
- stdout/stderr handling: `capture_output=True`, `text=True`, UTF-8 with replacement
- cwd: adapter `repo_root`
- timeout implementation: `subprocess.run(..., timeout=self.timeout_seconds)`
- default timeout: 1800 seconds
- timeout behavior: returns `ClaudeResult(exit_code=None, timed_out=True, stdout=<partial>, stderr=<partial>)`
- process termination: handled by Python `subprocess.run` on `TimeoutExpired`

The previous 90 second diagnostic did not reach the adapter timeout because the adapter default is 1800 seconds.

## Direct Claude CLI Evidence

Claude executable:

```text
C:\Users\Arghyadeep\.local\bin\claude.EXE
```

Claude version:

```text
2.1.278 (Claude Code)
```

Direct bounded CLI probes were run outside the adapter with 20 second hard timeouts.

### Direct default model probe

Command shape:

```text
claude -p CLAUDE_DIRECT_OK_20260922 --output-format text --permission-mode plan --safe-mode --setting-sources local --tools ""
```

Result:

```text
elapsed: 20.07s
exit: None
timeout: True
stdout: empty
stderr: empty
```

### Direct explicit haiku probe

Command shape:

```text
claude -p CLAUDE_DIRECT_OK_20260922 --model haiku --output-format text --permission-mode plan --safe-mode --setting-sources local --tools ""
```

Result:

```text
elapsed: 20.04s
exit: None
timeout: True
stdout: empty
stderr: empty
```

### Bare direct default probe

Command shape:

```text
claude -p CLAUDE_DIRECT_OK_20260922 --output-format text
```

Result:

```text
elapsed: 20.05s
exit: None
timeout: True
stdout: empty
stderr: empty
```

### Bare direct explicit haiku probe

Command shape:

```text
claude -p CLAUDE_DIRECT_OK_20260922 --model haiku --output-format text
```

Result:

```text
elapsed: 20.06s
exit: None
timeout: True
stdout: empty
stderr: empty
```

## Model Selection Evidence

Both default model selection and explicit `--model haiku` timed out with no stdout/stderr.

This rules out a demonstrated `haiku`-only adapter bug. The failure occurs before any provider response is returned for either default or explicit model mode.

`claude config get model` also hung and was manually interrupted, which further points to Claude Code runtime/config access rather than the bridge adapter's prompt handling.

## Claude Auth and Install Evidence

`claude doctor` completed successfully and reported:

```text
Running: native (2.1.278)
Search: OK (bundled)
Auto-updates: enabled
Last update attempt: success -> 2.1.278 (2026-09-21)
No installation issues found.
```

It also reported one invalid project setting:

```text
.mcp.json > mcpServers.glif: Missing environment variables: GLIF_API_TOKEN
```

`claude auth status` completed successfully and reported:

```text
loggedIn: true
authMethod: claude.ai
apiProvider: firstParty
subscriptionType: pro
```

## Exact Root Cause

Classification: A.

Direct Claude Code non-interactive provider calls hang outside the adapter, with both default model selection and explicit `haiku`, returning no stdout and no stderr before the bounded timeout.

The bridge adapter was not repaired because the demonstrated failure is external to the bridge implementation: the installed/authenticated Claude Code CLI can answer local metadata commands (`--version`, `doctor`, `auth status`) but does not return from actual `-p` provider calls in this environment.

## Adapter Evidence

Because direct Claude CLI calls fail outside the adapter, an adapter-only repair would risk hiding an external provider/CLI/config failure rather than fixing the bridge.

No bridge implementation change was made.

## Timeout and Cleanup Evidence

The direct CLI probes were bounded by Python subprocess timeouts and returned timeout records with empty stdout/stderr.

The existing adapter's default timeout is 1800 seconds; this explains the observed 90 second hang during the previous diagnostic. A timeout-shortening repair was not applied because direct CLI access itself is failing.

After the bounded probes, `Get-Process claude` showed Claude processes present. Some were the Windows Claude desktop app. Attempting to inspect command lines with `Get-CimInstance Win32_Process` was denied by Windows access controls, so no broad process kill was performed to avoid terminating unrelated user Claude app processes.

## Files Changed

Created this report:

```text
VECTOR_TECHNICAL_KNOWLEDGE/BRIDGE_CONNECTIVITY_REPAIR_REPORT.md
```

No bridge implementation files were changed.

No VECTOR production files were changed.

## Tests

No VECTOR test suite was run.

Bridge/provider diagnostics only:

- direct Claude default model probe
- direct Claude explicit `haiku` probe
- bare direct Claude default model probe
- bare direct Claude explicit `haiku` probe
- Claude doctor
- Claude auth status

## Actual Codex to Claude Response

No actual Claude provider response was returned.

Expected diagnostic response was not observed:

```text
CLAUDE_BRIDGE_RECEIVED_C2C_20260922
```

## Actual Claude to Codex Response

Not run.

Reason: Codex to Claude did not pass, so reverse testing was not permitted by the mission rules.

## Before and After Repository State

Before:

```text
HEAD: d3994e586de5689f4b5d6f1c209b97d65d0ca16d
branch: production-hardening-complete
```

After:

```text
HEAD: d3994e586de5689f4b5d6f1c209b97d65d0ca16d
branch: production-hardening-complete
```

The only intentional new file from this mission is this report. Existing dirty/runtime artifacts remain outside this mission.

## Final HEAD

No commit was created during this mission.

Final HEAD:

```text
d3994e586de5689f4b5d6f1c209b97d65d0ca16d
```

## Verdict

BRIDGE_REPAIR_BLOCKED - EXTERNAL CLAUDE/CODEX ACCESS REQUIRES USER ACTION
