// Approximate per-IP rate limiting with fixed-window KV counters.

export async function checkRateLimit(kv, ip, max, windowSeconds) {
  const nowSec = Math.floor(Date.now() / 1000);
  const windowStart = Math.floor(nowSec / windowSeconds) * windowSeconds;
  const key = `rl:${ip}:${windowStart}`;
  const used = Number((await kv.get(key)) ?? 0);
  if (used >= max) {
    return { allowed: false, retryAfter: Math.max(1, windowStart + windowSeconds - nowSec) };
  }
  await kv.put(key, String(used + 1), { expirationTtl: windowSeconds + 60 });
  return { allowed: true };
}
