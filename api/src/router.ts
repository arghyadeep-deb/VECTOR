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

const ALLOWED_PATHS = new Set([
  "/status",
  "/health",
  "/heartbeat",
  "/command",
  "/commands",
  "/memory/recent",
  "/council/history",
  "/security/recent",
  "/agents",
  "/goals",
]);

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

    if (
      !ALLOWED_PATHS.has(path) &&
      !path.startsWith("/command/") &&
      !path.startsWith("/commands/") &&
      !path.startsWith("/nodes/")
    ) {
      return json({ error: "not found", path }, 404);
    }

    if (path === "/status") return json({ status: "online", system: "VECTOR", layer: "cloudflare-worker" });
    if (path === "/health") return json({ status: "healthy" });

    if (path === "/heartbeat" && method === "POST") return this.heartbeatPost(request, env);
    if (path === "/heartbeat") return this.heartbeatGet(env);
    if ((path === "/command" || path === "/commands") && method === "POST") return this.commandPost(request, env);
    if (path.startsWith("/command/")) return this.commandStatus(env, decodeURIComponent(path.slice("/command/".length)));
    if (path.startsWith("/commands/") && path.endsWith("/result") && method === "POST") {
      const id = decodeURIComponent(path.slice("/commands/".length, -"/result".length));
      return this.commandResult(request, env, id);
    }
    if (path.startsWith("/commands/")) {
      return this.commandStatus(env, decodeURIComponent(path.slice("/commands/".length)));
    }
    if (path.startsWith("/nodes/") && path.endsWith("/poll") && method === "POST") {
      const nodeId = decodeURIComponent(path.slice("/nodes/".length, -"/poll".length));
      return this.nodePoll(request, env, nodeId);
    }

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
    const nodeId = String(data.node_id || data.nodeId || "legion-heavy-node");

    let commands: unknown[] = [];
    try {
      const res = await env.DB.prepare(
        "SELECT id,type,params,target_node,created_at FROM command_queue WHERE status='queued' AND (target_node=? OR target_node IS NULL OR target_node='') ORDER BY created_at LIMIT 50",
      ).bind(nodeId).all();
      commands = (res.results || []).map((r: any) => ({
        id: r.id,
        type: r.type,
        params: JSON.parse((r.params as string) || "{}"),
        target_node: r.target_node || nodeId,
        created_at: r.created_at,
      }));
      if (commands.length) {
        await env.DB.batch(
          (commands as any[]).map((c) =>
            env.DB.prepare("UPDATE command_queue SET status='delivered', delivered_at=?, claimed_at=?, updated_at=? WHERE id=?").bind(now, now, now, c.id),
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
    const targetNode = this.inferTargetNode(type, data, params);

    const id = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    const now = new Date().toISOString();
    try {
      await env.DB.prepare(
        "INSERT INTO command_queue (id,type,params,status,target_node,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
      )
        .bind(id, type, JSON.stringify(params), "queued", targetNode, now, now)
        .run();
    } catch (e) {
      return json({ error: "queue unavailable", detail: String(e) }, 503);
    }
    return json({ ok: true, command_id: id, target_node: targetNode, status: "queued" });
  }

  async commandStatus(env: Env, id: string): Promise<Response> {
    try {
      const row = await env.DB.prepare("SELECT id,type,status,target_node,result,error,created_at,delivered_at,claimed_at,completed_at,updated_at FROM command_queue WHERE id=?")
        .bind(id)
        .first();
      if (row) return json({ found: true, ...row });
    } catch {
      /* ignore */
    }
    return json({ found: false, command_id: id });
  }

  inferTargetNode(type: string, data: Record<string, any>, params: Record<string, any>): string {
    const explicit = data.target_node || data.targetNode || params.target_node || params.targetNode;
    if (explicit) return String(explicit);

    const capability = String(data.capability || params.capability || "").toLowerCase();
    if (capability === "lightweight" || capability === "termux" || capability === "requires_termux") {
      return "termux-room-node";
    }
    if (type === "wake_legion") return "termux-room-node";
    if (data.requires_legion || params.requires_legion || capability === "requires_legion") {
      return "legion-heavy-node";
    }

    // Preserve legacy behavior: generic remote commands are drained by Legion
    // through /heartbeat unless the caller explicitly marks them lightweight.
    return "legion-heavy-node";
  }

  async nodePoll(request: Request, env: Env, nodeId: string): Promise<Response> {
    let data: Record<string, any> = {};
    try {
      data = (await request.json()) as Record<string, any>;
    } catch {
      /* empty body ok */
    }
    const now = new Date().toISOString();
    await env.RATE_LIMIT_KV.put(`hb:${nodeId}`, JSON.stringify({ data, received_at: now }));
    if (nodeId === "legion-heavy-node") {
      await env.RATE_LIMIT_KV.put("hb:last", JSON.stringify({ data, received_at: now }));
    }

    let commands: unknown[] = [];
    try {
      const res = await env.DB.prepare(
        "SELECT id,type,params,target_node,created_at FROM command_queue WHERE status='queued' AND target_node=? ORDER BY created_at LIMIT 10",
      ).bind(nodeId).all();
      commands = (res.results || []).map((r: any) => ({
        id: r.id,
        type: r.type,
        params: JSON.parse((r.params as string) || "{}"),
        target_node: r.target_node,
        created_at: r.created_at,
      }));
      if (commands.length) {
        await env.DB.batch(
          (commands as any[]).map((c) =>
            env.DB.prepare("UPDATE command_queue SET status='running', claimed_at=?, updated_at=? WHERE id=? AND status='queued'").bind(now, now, c.id),
          ),
        );
      }
    } catch {
      /* D1 unavailable -> no commands this tick */
    }
    return json({ ok: true, node_id: nodeId, received_at: now, commands });
  }

  async commandResult(request: Request, env: Env, id: string): Promise<Response> {
    let data: Record<string, any> = {};
    try {
      data = (await request.json()) as Record<string, any>;
    } catch {
      return json({ error: "invalid json" }, 400);
    }
    const status = data.status === "failed" ? "failed" : data.status === "deferred" ? "deferred" : "done";
    const now = new Date().toISOString();
    try {
      await env.DB.prepare(
        "UPDATE command_queue SET status=?, result=?, error=?, completed_at=?, updated_at=? WHERE id=?",
      )
        .bind(status, JSON.stringify(data.result || {}), data.error || "", now, now, id)
        .run();
    } catch (e) {
      return json({ error: "queue unavailable", detail: String(e) }, 503);
    }
    return json({ ok: true, command_id: id, status });
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
