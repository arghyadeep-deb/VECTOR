import type { Env } from "./index";

/**
 * VECTOR unified cloud brain — runs entirely on the Cloudflare Worker (no Fly).
 *
 *  • command queue   → D1 (table `command_queue`)
 *  • heartbeat state → KV (key `hb:last`)
 *  • memory reads    → Supabase REST (cloud source of truth)
 *
 * The laptop POSTs /heartbeat every ~3s; we drain queued commands into the reply
 * (deliver-once). Commands submitted from any device via POST /command are queued
 * here; the laptop runs each through its permission gateway (this is not a bypass).
 */

const JSON_HEADERS: Record<string, string> = {
  "Content-Type": "application/json",
  "Access-Control-Allow-Origin": "*",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

function clampLimit(url: URL, def: number): number {
  const n = parseInt(url.searchParams.get("limit") || "", 10);
  return Number.isNaN(n) ? def : Math.min(Math.max(n, 1), 50);
}

async function supabaseEpisodic(
  env: Env,
  eventType: string | null,
  limit: number,
): Promise<unknown[] | null> {
  if (!env.SUPABASE_URL || !env.SUPABASE_KEY) return null;
  const params = new URLSearchParams({
    select: "id,event_type,content,tags,timestamp,source",
    order: "timestamp.desc",
    limit: String(limit),
  });
  if (eventType) params.set("event_type", `eq.${eventType}`);
  try {
    const r = await fetch(`${env.SUPABASE_URL}/rest/v1/episodic_memory?${params.toString()}`, {
      headers: { apikey: env.SUPABASE_KEY, Authorization: `Bearer ${env.SUPABASE_KEY}` },
    });
    if (r.ok) return (await r.json()) as unknown[];
  } catch {
    /* fall through */
  }
  return null;
}

export class Router {
  async handle(request: Request, env: Env, url: URL): Promise<Response> {
    const path = url.pathname;
    const method = request.method;

    if (path === "/status") return json({ status: "online", system: "VECTOR", layer: "cloudflare-worker" });
    if (path === "/health") return json({ status: "healthy" });

    if (path === "/heartbeat" && method === "POST") return this.heartbeatPost(request, env);
    if (path === "/heartbeat") return this.heartbeatGet(env);
    if (path === "/command" && method === "POST") return this.commandPost(request, env);
    if (path.startsWith("/command/")) return this.commandStatus(env, decodeURIComponent(path.slice("/command/".length)));

    if (path === "/memory/recent") return this.memory(env, null, clampLimit(url, 10), "events");
    if (path === "/council/history") return this.memory(env, "council_session", clampLimit(url, 5), "sessions");
    if (path === "/security/recent") return this.memory(env, "security_scan", clampLimit(url, 10), "events");
    if (path === "/agents") return this.fromHeartbeat(env, "agents");
    if (path === "/goals") return this.fromHeartbeat(env, "goals");

    return json({ error: "not found", path }, 404);
  }

  async heartbeatPost(request: Request, env: Env): Promise<Response> {
    let data: Record<string, unknown> = {};
    try {
      data = (await request.json()) as Record<string, unknown>;
    } catch {
      /* empty body ok */
    }
    const now = new Date().toISOString();
    await env.RATE_LIMIT_KV.put("hb:last", JSON.stringify({ data, received_at: now }));

    let commands: unknown[] = [];
    try {
      const res = await env.DB.prepare(
        "SELECT id,type,params,created_at FROM command_queue WHERE status='queued' ORDER BY created_at LIMIT 50",
      ).all();
      commands = (res.results || []).map((r: any) => ({
        id: r.id,
        type: r.type,
        params: JSON.parse((r.params as string) || "{}"),
        created_at: r.created_at,
      }));
      if (commands.length) {
        await env.DB.batch(
          (commands as any[]).map((c) =>
            env.DB.prepare("UPDATE command_queue SET status='delivered', delivered_at=? WHERE id=?").bind(now, c.id),
          ),
        );
      }
    } catch {
      /* D1 unavailable → no commands this tick */
    }
    return json({ ok: true, received_at: now, commands });
  }

  async heartbeatGet(env: Env): Promise<Response> {
    const stored = await env.RATE_LIMIT_KV.get("hb:last");
    return json(stored ? JSON.parse(stored) : { last_heartbeat: null, data: {} });
  }

  async commandPost(request: Request, env: Env): Promise<Response> {
    let data: Record<string, any> = {};
    try {
      data = (await request.json()) as Record<string, any>;
    } catch {
      /* ignore */
    }
    let type = (data.type || "").trim();
    let params = data.params || {};
    if (!type && data.text) {
      type = "command";
      params = { text: String(data.text), ...params };
    }
    if (!type) return json({ error: "command 'type' or 'text' is required" }, 400);

    const id = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    const now = new Date().toISOString();
    try {
      await env.DB.prepare(
        "INSERT INTO command_queue (id,type,params,status,created_at) VALUES (?,?,?,?,?)",
      )
        .bind(id, type, JSON.stringify(params), "queued", now)
        .run();
    } catch (e) {
      return json({ error: "queue unavailable", detail: String(e) }, 503);
    }
    return json({ ok: true, command_id: id });
  }

  async commandStatus(env: Env, id: string): Promise<Response> {
    try {
      const row = await env.DB.prepare("SELECT id,type,status,created_at,delivered_at FROM command_queue WHERE id=?")
        .bind(id)
        .first();
      if (row) return json({ found: true, ...row });
    } catch {
      /* ignore */
    }
    return json({ found: false, command_id: id });
  }

  async memory(env: Env, eventType: string | null, limit: number, key: string): Promise<Response> {
    const rows = await supabaseEpisodic(env, eventType, limit);
    if (rows === null) return json({ [key]: [], count: 0, source: "unconfigured" });
    return json({ [key]: rows, count: rows.length, source: "supabase" });
  }

  async fromHeartbeat(env: Env, kind: string): Promise<Response> {
    const stored = await env.RATE_LIMIT_KV.get("hb:last");
    const hb = stored ? JSON.parse(stored).data || {} : {};
    if (kind === "agents") {
      return json({ agents: [], count: hb.agents_alive || hb.total_agents || 0, source: "heartbeat" });
    }
    return json({ immediate_actions: hb.immediate_actions || [], source: "heartbeat" });
  }
}
