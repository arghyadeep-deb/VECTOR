import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("harness smoke check", () => {
  it("public /status endpoint responds 200", async () => {
    const res = await SELF.fetch("https://example.com/status");
    expect(res.status).toBe(200);
  });
});
