/**
 * VECTOR Cloudflare Worker — the unified cloud brain (no Fly).
 * Command queue (D1) + heartbeat (KV) + memory reads (Supabase), with Bearer
 * auth and KV rate limiting. The laptop polls this Worker for remote commands.
 */
import { Router } from "./router";
import { verifyAuth } from "./auth";
import { checkRateLimit } from "./rate_limiter";

export interface Env {
  VECTOR_API_KEY: string;
  RATE_LIMIT_KV: KVNamespace;
  DB: D1Database;
  SUPABASE_URL: string;
  SUPABASE_KEY: string;
}

const router = new Router();

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Authorization, Content-Type",
        },
      });
    }

    // Public endpoints — no auth required
    if (url.pathname === "/status" || url.pathname === "/health") {
      return router.handle(request, env, url);
    }

    // Auth check
    const authError = verifyAuth(request, env);
    if (authError) return authError;

    // Rate limiting. The node poll paths (/heartbeat, /nodes/*/poll) are the
    // authenticated machine-to-machine hot path — the laptop heartbeats every
    // ~3s (~20 req/min), which a 10/min bucket 429'd half the time and the
    // client swallowed silently. They get their own generous bucket; every
    // other route keeps the strict human-scale limit.
    const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
    const isNodePoll =
      url.pathname === "/heartbeat" ||
      (url.pathname.startsWith("/nodes/") && url.pathname.endsWith("/poll"));
    const limited = isNodePoll
      ? await checkRateLimit(env.RATE_LIMIT_KV, `poll:${ip}`, 60, 60)
      : await checkRateLimit(env.RATE_LIMIT_KV, ip, 10, 60);
    if (limited) {
      return new Response(JSON.stringify({ error: "rate limited" }), {
        status: 429,
        headers: { "Content-Type": "application/json" },
      });
    }

    return router.handle(request, env, url);
  },
};
