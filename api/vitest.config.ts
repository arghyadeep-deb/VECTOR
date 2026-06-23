import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

// Isolated test bindings only — deliberately NOT the real provisioned
// database_id/KV id in wrangler.toml. Miniflare creates fresh in-memory
// D1/KV for every test run; nothing here ever touches production data.
export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        main: "./src/index.ts",
        miniflare: {
          compatibilityDate: "2024-09-23",
          compatibilityFlags: ["nodejs_compat"],
          kvNamespaces: ["RATE_LIMIT_KV"],
          d1Databases: ["DB"],
          bindings: {
            VECTOR_API_KEY: "test-key-local-only",
            SUPABASE_URL: "",
            SUPABASE_KEY: "",
          },
        },
      },
    },
  },
});
