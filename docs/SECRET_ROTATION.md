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
scan likewise found code references, docs, examples, and tests. This does not
clear git history: `certs/vector.key` must still be purged from history and any
credential material that ever used it must be rotated before pushing or sharing
the repository.

I did not run `git filter-repo`, `git reset`, or any destructive cleanup here.
Those are owner-controlled history/worktree operations.
