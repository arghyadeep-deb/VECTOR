/**
 * VECTOR Cloudflare Worker — API gateway
 * Proxies authenticated requests to brain server (Fly.io)
 * with rate limiting via KV.
 */
import { Router } from "./router";
import { verifyAuth } from "./auth";
import { checkRateLimit } from "./rate_limiter";

export interface Env {
  VECTOR_API_KEY: string;
  BRAIN_SERVER_URL: string;
  RATE_LIMIT_KV: KVNamespace;
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
      return router.proxy(request, env, url.pathname);
    }

    // Auth check
    const authError = verifyAuth(request, env);
    if (authError) return authError;

    // Rate limiting (10 req/min per IP)
    const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
    const limited = await checkRateLimit(env.RATE_LIMIT_KV, ip, 10, 60);
    if (limited) {
      return new Response(JSON.stringify({ error: "rate limited" }), {
        status: 429,
        headers: { "Content-Type": "application/json" },
      });
    }

    return router.handle(request, env, url);
  },
};
