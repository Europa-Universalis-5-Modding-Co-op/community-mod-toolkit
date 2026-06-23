// Files the issue under the mod's repo. Prefers a GitHub App (bot identity,
// org-managed); falls back to a fine-grained PAT when GH_PAT is set.

const API = "https://api.github.com";
const UA = "eu5-bug-reporter";

export class GitHubError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "GitHubError";
    this.status = status;
  }
}

export async function createIssue(env, repoFullName, { title, body, labels }) {
  const [owner, repo] = repoFullName.split("/");
  if (!owner || !repo) throw new GitHubError(`bad repo: ${repoFullName}`, 0);
  const auth = await resolveAuth(env, owner, repo);
  const res = await fetch(`${API}/repos/${owner}/${repo}/issues`, {
    method: "POST",
    headers: { ...auth, ...jsonHeaders() },
    body: JSON.stringify({ title, body, labels }),
  });
  if (!res.ok) {
    throw new GitHubError(`issue create ${res.status}: ${await res.text()}`, res.status);
  }
  const issue = await res.json();
  return { url: issue.html_url, number: issue.number };
}

async function resolveAuth(env, owner, repo) {
  if (env.GH_PAT) return { Authorization: `token ${env.GH_PAT}` };
  const token = await installationToken(env, owner, repo);
  return { Authorization: `token ${token}` };
}

async function installationToken(env, owner, repo) {
  const cacheKey = `ghtoken:${owner}`;
  const cached = await env.KV.get(cacheKey, "json");
  const nowSec = Math.floor(Date.now() / 1000);
  if (cached && cached.exp - 300 > nowSec) return cached.token;

  const jwt = await buildAppJwt(env);
  const installationId = env.GH_APP_INSTALLATION_ID || (await lookupInstallationId(jwt, owner, repo));
  const res = await fetch(`${API}/app/installations/${installationId}/access_tokens`, {
    method: "POST",
    headers: { ...bearer(jwt), ...jsonHeaders() },
  });
  if (!res.ok) throw new GitHubError(`token exchange ${res.status}: ${await res.text()}`, res.status);
  const tok = await res.json();
  const expSec = Math.floor(new Date(tok.expires_at).getTime() / 1000);
  await env.KV.put(cacheKey, JSON.stringify({ token: tok.token, exp: expSec }), {
    expirationTtl: Math.max(60, expSec - nowSec),
  });
  return tok.token;
}

async function lookupInstallationId(jwt, owner, repo) {
  const res = await fetch(`${API}/repos/${owner}/${repo}/installation`, { headers: bearer(jwt) });
  if (!res.ok) throw new GitHubError(`installation lookup ${res.status}: ${await res.text()}`, res.status);
  return (await res.json()).id;
}

async function buildAppJwt(env) {
  const key = await importPrivateKey(env.GH_APP_PRIVATE_KEY);
  const nowSec = Math.floor(Date.now() / 1000);
  // iat backdated 60s for clock skew; iat-to-exp stays under GitHub's 10-minute cap.
  const header = b64urlString(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = b64urlString(JSON.stringify({ iat: nowSec - 60, exp: nowSec + 540, iss: String(env.GH_APP_ID) }));
  const signingInput = `${header}.${payload}`;
  const sig = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(signingInput),
  );
  return `${signingInput}.${b64urlBytes(new Uint8Array(sig))}`;
}

function importPrivateKey(pem) {
  const normalized = pem.includes("\\n") ? pem.replace(/\\n/g, "\n") : pem;
  const der = pemBody(normalized);
  return crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

function pemBody(pem) {
  const b64 = pem
    .replace(/-----BEGIN [^-]+-----/, "")
    .replace(/-----END [^-]+-----/, "")
    .replace(/\s+/g, "");
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

function b64urlBytes(bytes) {
  let str = "";
  for (let i = 0; i < bytes.length; i++) str += String.fromCharCode(bytes[i]);
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlString(str) {
  return b64urlBytes(new TextEncoder().encode(str));
}

function bearer(jwt) {
  return { Authorization: `Bearer ${jwt}`, Accept: "application/vnd.github+json", "User-Agent": UA, "X-GitHub-Api-Version": "2022-11-28" };
}

function jsonHeaders() {
  return { Accept: "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": UA, "X-GitHub-Api-Version": "2022-11-28" };
}
