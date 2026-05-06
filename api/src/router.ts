import type { Env } from "./index";

const ALLOWED_PATHS = new Set([
  "/status",
  "/health",
  "/agents",
  "/memory/recent",
  "/goals",
  "/council/history",
  "/security/recent",
  "/heartbeat",
]);

export class Router {
  async proxy(request: Request, env: Env, path: string): Promise<Response> {
    const target = `${env.BRAIN_SERVER_URL}${path}`;
    try {
      const upstream = await fetch(target, {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body: request.method !== "GET" ? request.body : undefined,
      });
      const data = await upstream.json();
      return new Response(JSON.stringify(data), {
        status: upstream.status,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: "upstream unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
  }

  async handle(request: Request, env: Env, url: URL): Promise<Response> {
    const path = url.pathname;

    if (!ALLOWED_PATHS.has(path)) {
      return new Response(JSON.stringify({ error: "not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Forward query params
    const targetUrl = `${env.BRAIN_SERVER_URL}${path}${url.search}`;
    try {
      const upstream = await fetch(targetUrl, {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body: request.method !== "GET" ? request.body : undefined,
      });
      const data = await upstream.json();
      return new Response(JSON.stringify(data), {
        status: upstream.status,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: "upstream unavailable", path }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
  }
}
