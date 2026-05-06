/**
 * KV-based sliding window rate limiter.
 * key: `rl:{ip}`, value: JSON array of request timestamps (Unix ms).
 */
export async function checkRateLimit(
  kv: KVNamespace,
  key: string,
  maxRequests: number,
  windowSec: number
): Promise<boolean> {
  const kvKey = `rl:${key}`;
  const now = Date.now();
  const windowMs = windowSec * 1000;

  let timestamps: number[] = [];
  try {
    const stored = await kv.get(kvKey);
    if (stored) timestamps = JSON.parse(stored);
  } catch {
    return false;
  }

  // Drop timestamps outside the window
  timestamps = timestamps.filter((t) => now - t < windowMs);

  if (timestamps.length >= maxRequests) {
    return true; // rate limited
  }

  timestamps.push(now);
  await kv.put(kvKey, JSON.stringify(timestamps), { expirationTtl: windowSec * 2 });
  return false;
}
