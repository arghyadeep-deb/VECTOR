# Investigation: channels/comms and core/mining origin

**Date:** 2026-10-08  
**Scope:** Read-only repository and git-history investigation for OD-6 and G6. No disposition was executed.

## Investigation 1: `channels/` versus `comms/`

### Directory inventory

Three matching directories exist in the repository. Counts below distinguish git-tracked source files from files physically present in the working tree, because compiled `__pycache__` artifacts almost double the latter two counts.

| Directory (full repository-relative path) | Tracked files | Physical files | Role visible from contents |
|---|---:|---:|---|
| `core/engine/channels/` | 2 | 4 | Small engine-level package (`models.py`, `rules.py`), not a platform adapter tree |
| `vectorcode/src/channels/` | 45 | 86 | `BaseChannel`-style platform transports plus bulk sending and adapters; no `__init__.py` |
| `vectorcode/src/comms/` | 58 | 116 | Mixed tree: higher-level bots/hub/session/inbound routing **and** duplicated `BaseChannel` transports |

There is no repository-root `channels/` or `comms/`, and no `core/channels/` or `core/comms/`. The relevant competing pair is therefore `vectorcode/src/channels/` and `vectorcode/src/comms/`; `core/engine/channels/` is unrelated.

### Twitter comparison

The two Twitter modules implement the same capability, not two architectural layers:

- `vectorcode/src/channels/twitter_channel.py` (341 source lines as reported by `rg`, 285 nonblank/PowerShell-counted lines) and `vectorcode/src/comms/twitter_channel.py` (328/280) are near-copies of the same OAuth 1.0a Twitter API v2 `BaseChannel`. Both register the identical key with the same shared `ChannelRegistry` (`"twitter"`), poll mentions, send/reply to tweets, publish events, and export `TwitterChannel`.
- The `channels` copy has the more recent targeted change: commit `077f9bada` on 2026-10-06 added numeric snowflake comparison through `_is_newer_tweet_id()` and its regression test. The `comms` copy's latest change is `e27cc6e75`, also 2026-10-06, from a broad comms hardening batch. Both ultimately trace to the same May 2026 absorption history (`5655db625`/`122179713`), so neither is an independently designed implementation.
- The `channels` copy uses the current shim paths (`vectorcode.src.channels._abc`, `vectorcode.src.core.events`, `vectorcode.src.core.registry`). The `comms` copy still uses the older `comms._abc` and `vc_core` paths. Importantly, `channels/_abc.py` is itself a seven-line compatibility re-export of `comms._abc`; the data model is shared even though the concrete transports were duplicated.
- Neither Twitter module has a direct production importer outside the two trees. Tests import both (`test_channels_audit_regressions.py` imports the `channels` helper; `test_vectorcode_comms_batch_b_regressions.py` imports the `comms` class). Twitter recipes name the registry key but do not import either implementation.
- The earlier OD-6 statement that `agent_manager_routes.py` imports Twitter from both trees does not match the current code. It merely executes `import vectorcode.src.channels`; because `channels/` has no `__init__.py`, that namespace import does not import/register `twitter_channel.py`. The registry also raises `ValueError` on a duplicate key; it does **not** silently let the second registration win. If both Twitter modules are imported, import order produces a hard duplicate-registration failure.

On completeness/currentness, the `channels` copy is marginally ahead. On real callers, the result is a tie at zero direct production callers. This is dead/unwired duplication today, but still unsafe because tests or future discovery code can import both into the shared registry.

### Other-platform comparisons

#### Discord

- `channels/discord_channel.py` and `comms/discord_channel.py` are the same synchronous `BaseChannel` gateway/webhook transport with the same `"discord"` registration and almost identical method surfaces. Their first history is the same absorption commit (`4a585a161`, 2026-05-16). The channels copy was last changed 2026-10-03 (`8f9ca3eaa`); the comms copy was last changed minutes later in another audit batch (`5aabc5835`).
- The production cloud communications service directly resolves `vectorcode.src.channels.discord_channel.DiscordChannel`. No production code directly imports `comms.discord_channel`.
- `comms/discord_bot.py` is genuinely different: a compact asynchronous bot used by `core/communications/hub.py`. It is an orchestration-facing wrapper, not the duplicated `BaseChannel` transport, and should not be conflated with `comms/discord_channel.py`.

#### Slack

- There is no same-named duplicated transport pair: `channels/slack.py` is the full synchronous `SlackChannel` transport and is directly resolved by `cloud/comms_service/service.py`; `comms/slack_bot.py` is a small async bot used by `core/communications/hub.py`. Those are legitimate lower-level transport versus higher-level runtime interfaces.
- `comms/slack_daemon.py` is a real 170-line daemon used by `server/agent_manager_routes.py`. `channels/slack_daemon.py` is only a 17-line compatibility shim re-exporting that canonical comms daemon, and the regression test explicitly names `comms` as canonical. This is a good example of the intended boundary: orchestration/daemon in `comms`, compatibility exposure from `channels` only where needed.

#### WhatsApp

- `channels/whatsapp.py` is a full registered `BaseChannel` transport directly resolved by the cloud communications service. `comms/whatsapp_bot.py` is a small async bot directly loaded by `core/communications/hub.py`; these are genuinely different layers.
- `channels/whatsapp_baileys.py` and `comms/whatsapp_baileys.py`, however, are another same-capability near-copy pair (286 counted lines apiece) and register the same `"whatsapp_baileys"` key. Tests currently target both namespaces, but no external production importer selects either concrete file directly.

Signal shows the same duplicate-adapter problem as Twitter: `signal_channel.py` exists in both trees at 108 counted lines and both register `"signal"`; meanwhile `comms/signal_bot.py` is the distinct higher-level bot actually loaded by the core hub. Across all registry decorators, `channels` defines 31 keys and `comms` defines 23; 22 comms keys overlap channels keys. The split is therefore systemic, not Twitter-specific, but only the duplicated `*Channel` subset is erroneous. The bot, daemon, session, inbound, webhook-server, and platform-adapter facilities in `comms` are real additional capabilities.

**Recommendation:** Make `vectorcode/src/channels/` canonical for concrete registered `BaseChannel` transports, because the cloud production service and channel agent/tool abstractions already consume that interface and its Twitter copy has the newest targeted correctness fix. Keep `vectorcode/src/comms/` as the higher-level messaging/orchestration layer (`*_bot.py`, `messenger.py`, `session_manager.py`, `inbound.py`, daemons, webhook server, and platform adapters). Merge any fixes found only in the 22 overlapping comms transport modules into `channels`, redirect tests/imports, and then delete or reduce those duplicated comms transports to explicit compatibility re-exports that do **not** re-register keys. Do not delete the whole `comms` tree. Also add explicit package/discovery wiring as a separate implementation task: the current namespace-only `channels` import does not populate the registry. Twitter specifically should retain the `channels` implementation and retire `comms/twitter_channel.py` after reconciliation.

## Investigation 2: `core/mining/` origin

### File review and embedded provenance

The current tree contains exactly 14 tracked files:

`__init__.py`, `_abc.py`, `_constants.py`, `_install.py`, `_metrics.py`, `_miner_loop_main.py`, `_mps_miner_loop_main.py`, `_pearl_subprocess.py`, `apple_mps_pearl.py`, `constants.py`, `cpu_pearl.py`, `discovery.py`, `models.py`, and `vllm_pearl.py`.

All 14 were read. There are no per-file copyright or license headers. There is, however, direct and repeated external-origin evidence:

- `core/mining/__init__.py` begins `VECTOR module -- ported from VectorCode` and says the utilities were “Pulled from VectorCode's Pearl mining subsystem.” `discovery.py` and `models.py` carry the same port marker.
- `constants.py` says it contains a Pearl reference “OJ has tested against”; `_miner_loop_main.py` says “The parent OJ process spawns this module”; `vllm_pearl.py` retains the original-style path comment `src/vector/mining/vllm_pearl.py`. Here OJ is OpenJarvis, consistent with the introduction commit.
- The implementation is an integration layer around the external Pearl project and its packages (`pearl_mining`, `pearl_gateway`, `miner_base`), with `PEARL_REPO` explicitly set to `https://github.com/pearl-research-labs/pearl.git`. Several comments document verified upstream Pearl APIs and paths. This use of dependencies alone would not make VECTOR's glue code vendored, but the port markers and commit provenance do.
- A parallel `vectorcode/src/mining/` still exists with 13 files and matching basenames for 9 of the core files. The files have since diverged through local fixes and partial migration, but the parallel structure and shared APIs corroborate a port rather than a fresh owner-authored subsystem.

### Git provenance

The history is conclusive:

- Ten foundational files first appeared together in commit `5655db625dbea1de24fb8e57dcfea76846d67887` on 2026-05-15. Its subject is **“feat(vc): absorb remaining OpenJarvis gaps — 100% parity achieved”**. The body explicitly lists `core/mining/ (8 files)` among missing OpenJarvis module groups being absorbed and the diff creates `_constants.py`, `_install.py`, `_metrics.py`, `_miner_loop_main.py`, `_mps_miner_loop_main.py`, `_pearl_subprocess.py`, `_stubs.py`, `apple_mps_pearl.py`, `cpu_pearl.py`, and `vllm_pearl.py` (the body’s “8” is a stale count; the diff lists ten).
- `_stubs.py` was renamed `_abc.py` in commit `c7d2a676d` on 2026-05-21. That was a mechanical repository-wide rename plus mining cleanup, not a new implementation.
- `__init__.py`, `constants.py`, `discovery.py`, and `models.py` first appear under commit `122179713` on 2026-05-15, **“feat(vc): deabsorb all absorbed modules — zero third-party traces.”** That message describes renaming/debranding absorbed code, not independent authorship.
- Later commits are local maintenance: the May 30 `test` commit updates the Pearl integration; September repairs broken imports; October fixes import regressions and makes `Sidecar.write()` durable with fsync/explicit encoding (`0f6673fa1`, 2026-10-07). These modifications are valid local derivative maintenance and do not erase the original provenance.

### Documentation and Brain-vault evidence

- `docs/OPEN_ISSUES.md` repeatedly calls `core/mining` an already documented VectorCode port and, at lines around 1422/1474, records the owner correction that it is a vendored third-party port with unidentified upstream licensing. The later audit inconsistency came from treating it as ordinary code, not from new evidence disproving the port.
- The Brain conversation record for 2026-09-26 likewise says the running audit was corrected to stop line-by-line treatment because `core/mining` was “confirmed vendored — an unidentified-license vectorcode port.” No Brain note supplies contrary owner-authorship evidence.
- `VECTOR_TECHNICAL_KNOWLEDGE/03_VECTOR_VS_REPOSITORY.md` labels it VECTOR core/data mining, but this is an architectural placement label, not provenance evidence. Other knowledge files discuss reachability and broken imports without claiming original authorship.
- Most importantly, this repository already contains `vectorcode/LICENSES/Apache-2.0-OpenJarvis.txt`. Thus the immediate upstream named by the introduction commit is not actually license-unknown inside the current repository: the preserved OpenJarvis license is Apache-2.0. The Pearl project/packages are dependencies used through their APIs; if any upstream Pearl source was copied into these files (rather than merely called), that narrower question would require an upstream textual comparison, but nothing in the local history changes the demonstrated OpenJarvis-derived origin.

The expected local notice pattern is shown by `districts/investment/vector_finagent/NOTICE.md`: it identifies the third-party source, license, non-core status, selected use, and VECTOR integration boundary. `core/mining/` lacks such a notice despite stronger provenance evidence than several already-noticed trees.

### Conclusion

`core/mining/` is not purely hand-written/owner-authored VECTOR code. It is an OpenJarvis-derived/VectorCode-ported component that has subsequently received substantial owner/VECTOR modifications. The 2026-09-29 vendored classification was correct in substance; the “unclear upstream license” portion is stale or incomplete because the repository preserves OpenJarvis's Apache-2.0 text. Giving the derivative code full-depth review and fixing it was not evidence of owner authorship and does not change its attribution requirements.

**Recommendation:** Keep the vendored/derived classification and add a component-local `core/mining/NOTICE.md` in a future, separately authorized change. The notice should identify OpenJarvis as the immediate source, reference `vectorcode/LICENSES/Apache-2.0-OpenJarvis.txt`, describe the May 15 absorption plus later VECTOR modifications, identify Pearl as the external subsystem/dependency, and avoid claiming that all current lines are untouched upstream code. G6 should be corrected from “classification ambiguous” to “OpenJarvis-derived, locally modified; NOTICE missing.”
