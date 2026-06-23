// Server-side Turnstile verification that gates the upload grant.

const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

export async function verifyTurnstile(token, secret, remoteIp) {
  if (!token || !secret) return false;
  const body = new FormData();
  body.append("secret", secret);
  body.append("response", token);
  if (remoteIp) body.append("remoteip", remoteIp);
  const res = await fetch(SITEVERIFY_URL, { method: "POST", body });
  if (!res.ok) return false;
  const data = await res.json().catch(() => ({}));
  return data.success === true;
}
