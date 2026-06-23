// KNOWN LOCAL LIMITATION (confirmed 2026-06-23, do not re-debug this without
// reading this comment first): @cloudflare/vitest-pool-workers' workerd-based
// module loader cannot resolve modules when the project's real filesystem
// path contains a literal space -- this repo lives under
// ".../V.E.C.T.O.R. Codebase/", which breaks it unconditionally. Confirmed
// via repeated direct runs (real error: "No such module
// .../node_modules/vitest/dist/file:/...V.E.C.T.O.R.%20Codebase/.../
// threads.js" -- workerd double-encodes/mis-resolves the space). Also
// confirmed a Windows junction to a space-free path does NOT help: Node's
// module resolution sees through the junction to the real canonical path
// regardless. This is an upstream workerd/miniflare path-handling bug, not
// a bug in this config or in router.ts/index.ts/auth.ts (those were already
// independently verified secure by direct code reading -- see
// docs/repo_analysis/_MASTER_TODO.md §3 item 6).
//
// This file is real, correct scaffolding -- it WILL run wherever the
// project path has no spaces (CI on Linux, e.g. GitHub Actions, or a local
// clone at a space-free path). It has never successfully executed in this
// local Windows environment, so do not trust it as "passing" without
// running it somewhere the path issue doesn't apply.
import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("harness smoke check", () => {
  it("public /status endpoint responds 200", async () => {
    const res = await SELF.fetch("https://example.com/status");
    expect(res.status).toBe(200);
  });
});
