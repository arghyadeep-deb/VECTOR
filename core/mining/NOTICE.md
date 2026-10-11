# Third-Party Vendored Code Notice

This directory contains code derived from OpenJarvis.
Ten of its files (`_constants.py`, `_install.py`, `_metrics.py`,
`_miner_loop_main.py`, `_mps_miner_loop_main.py`, `_pearl_subprocess.py`,
`_stubs.py`, `apple_mps_pearl.py`, `cpu_pearl.py`, `vllm_pearl.py`) were
introduced together in commit `5655db625` (2026-05-15, "feat(vc): absorb
remaining OpenJarvis gaps -- 100% parity achieved"), which explicitly lists
`core/mining/` among the OpenJarvis module groups being absorbed. Internal
comments retain OpenJarvis-origin markers (e.g. "OJ has tested against...",
"The parent OJ process spawns this module").
OpenJarvis's license is Apache-2.0; the full text is preserved at
`vectorcode/LICENSES/Apache-2.0-OpenJarvis.txt`.
This is not a claim that every current line is untouched upstream code --
this tree has since received substantial owner/VECTOR modifications and bug
fixes (including real correctness fixes to `_abc.py`'s `Sidecar.write()`).
Pearl is an external mining subsystem/dependency these modules call into via
its own APIs and subprocess interface; VECTOR does not vendor Pearl itself.
See `docs/design/investigation-2026-10-08-channels-comms-and-mining-origin.md`
for the full provenance investigation.
