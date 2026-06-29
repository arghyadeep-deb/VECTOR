# Secret Rotation Runbook

Deleting a secret from the current tree does not make it safe. If a private
key, token, or API credential was ever committed, treat it as compromised.

Required steps:

1. Rotate or revoke the exposed credential with the provider or local service.
2. Remove the secret from the current tree and keep it ignored.
3. Purge the old bytes from git history before pushing or sharing the repo.
4. Coordinate the rewrite with every clone/fork owner because commit IDs change.

For the removed TLS key:

```powershell
# After installing git-filter-repo:
git filter-repo --path certs/vector.key --invert-paths
```

After the rewrite, regenerate any TLS material that depended on the removed key
and update deployment secrets through the target secret manager, not source
control.

Current-tree check from 2026-06-27:

```powershell
rg -n "BEGIN .*PRIVATE KEY" -g "!*node_modules*" -g "!*.png" -g "!*.jpg" -g "!*.wav"
rg -n "ghp_|xox[baprs]-|sk-[A-Za-z0-9]{20,}|SUPABASE_KEY|VECTOR_API_KEY|POLICY_AUD|TEAM_DOMAIN" -g "!*node_modules*"
```

The private-key scan only found detector patterns, tests, docs, and UI example
placeholders; it did not find a live PEM key in the current tree. The token/key
scan likewise found code references, docs, examples, and tests.

## History purge — ✅ DONE (2026-06-29)

The history purge described above was executed. All 9 private-key/secret blobs
that were in git history have been removed with `git filter-repo --invert-paths`:

- `certs/vector.key` (TLS key)
- `districts/intelligence/shadowbroker_server/data/_domain_keys/*.key`
  (`dm_alias`, `gate_persona`, `gate_session`, `gates`, `root`, `transport`)
- `districts/intelligence/shadowbroker_server/data/dm_token_pepper.key`
- `districts/intelligence/shadowbroker_server/data/wormhole_secure_store.key`

Verified afterward: `git rev-list --objects --all | grep -E '\.key$|\.pem$'`
returns **nothing**, `git fsck --full` is clean, all commits preserved. These
paths are already covered by `.gitignore` (`*.key`, `*.pem`, `certs/*.key`,
`districts/intelligence/**/*.key`) so they cannot be re-committed.

**Rotation — owner's call, but likely not required.** The repo had **never been
successfully pushed** at the time of the purge (no `origin/*` tracking branches;
pushes were blocked by oversized blobs until this session). So these keys never
left the local machine — purging before the first push means they were never
exposed. Rotate anyway only if this working copy was ever shared by other means
(a copied `.git`, a backup uploaded somewhere, etc.). Regenerating TLS material
and updating deployment secrets through the target secret manager (not source
control) remains the right move if you do rotate.

A full `.git` backup was taken before the rewrite
(`../vector_git_backup3_*`); delete it once the force-push is confirmed.
