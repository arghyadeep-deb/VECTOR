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
// clone at a space-free path). In this checkout, run it through `npm test`;
// api/scripts/run-vitest-no-space.mjs copies the package to a temporary
// space-free path first. Verified locally on 2026-06-27: 5/5 tests passed.
import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("harness smoke check", () => {
  it("public /status endpoint responds 200", async () => {
    const res = await SELF.fetch("https://example.com/status");
    expect(res.status).toBe(200);
  });

  it("protected routes require bearer auth", async () => {
    const res = await SELF.fetch("https://example.com/command", { method: "POST" });
    expect(res.status).toBe(401);
  });

  it("protected routes reject invalid bearer auth", async () => {
    const res = await SELF.fetch("https://example.com/command", {
      method: "POST",
      headers: { Authorization: "Bearer wrong-key" },
    });
    expect(res.status).toBe(403);
  });

  it("protected routes accept configured bearer auth", async () => {
    const res = await SELF.fetch("https://example.com/memory/recent", {
      headers: { Authorization: "Bearer test-key-local-only" },
    });
    expect(res.status).toBe(200);
    const body = await res.json() as { source: string; count: number };
    expect(body.source).toBe("unconfigured");
    expect(body.count).toBe(0);
  });

  it("command submission validates payload before queueing", async () => {
    const res = await SELF.fetch("https://example.com/command", {
      method: "POST",
      headers: {
        Authorization: "Bearer test-key-local-only",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });
});
