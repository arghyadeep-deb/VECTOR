import type { Env } from "./index";

/** Constant-time string comparison — `!==` leaks the key via response timing.
 *  Mirrors core/api/auth.py which uses hmac.compare_digest locally. */
function timingSafeEqualStr(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  if (ab.byteLength !== bb.byteLength) return false;
  // Cloudflare Workers runtime extension
  return (crypto.subtle as any).timingSafeEqual(ab, bb);
}

export function verifyAuth(request: Request, env: Env): Response | null {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const token = authHeader.slice(7);
  if (!env.VECTOR_API_KEY || !timingSafeEqualStr(token, env.VECTOR_API_KEY)) {
    return new Response(JSON.stringify({ error: "forbidden" }), {
      status: 403,
      headers: { "Content-Type": "application/json" },
    });
  }

  return null;
}
