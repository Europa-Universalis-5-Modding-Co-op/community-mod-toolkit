// Reads the deployment config the wizard bakes into wrangler.toml [vars].

export function getSiteConfig(env) {
  return {
    siteDomain: env.SITE_DOMAIN,
    savesDomain: env.SAVES_DOMAIN,
    turnstileSitekey: env.TURNSTILE_SITEKEY,
    maxUploadBytes: Number(env.MAX_UPLOAD_BYTES),
    presignExpirySeconds: Number(env.PRESIGN_EXPIRY_SECONDS),
    rateLimitMax: Number(env.RATE_LIMIT_MAX),
    rateLimitWindowSeconds: Number(env.RATE_LIMIT_WINDOW_SECONDS),
    defaultLabels: asArray(env.DEFAULT_LABELS),
  };
}

export function findMod(env, modId) {
  if (!modId) return null;
  return asArray(env.MODS).find((mod) => mod.id === modId) ?? null;
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string" && value.trim()) {
    try {
      return JSON.parse(value);
    } catch {
      return [];
    }
  }
  return [];
}
