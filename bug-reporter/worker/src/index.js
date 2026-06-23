// Router for the bug-report intake API. The save itself never passes through
// here: the browser PUTs it straight to R2 via a presigned URL minted at
// /api/presign, and /api/submit only verifies the finished object and files it.

import { getSiteConfig, findMod } from "./config.js";
import { verifyTurnstile } from "./turnstile.js";
import { checkRateLimit } from "./ratelimit.js";
import { validateFields, hasSavMagic } from "./validate.js";
import { presignPut, headObject, getObjectRange, deleteObject, publicUrl } from "./r2.js";
import { createIssue } from "./github.js";
import { postDiscord, buildEmbed } from "./discord.js";

const PENDING_TTL_SECONDS = 1800;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return withCors(request, env, new Response(null, { status: 204 }));
    try {
      if (url.pathname === "/api/config" && request.method === "GET") {
        return withCors(request, env, await handleConfig(request, env));
      }
      if (url.pathname === "/api/presign" && request.method === "POST") {
        return withCors(request, env, await handlePresign(request, env));
      }
      if (url.pathname === "/api/submit" && request.method === "POST") {
        return withCors(request, env, await handleSubmit(request, env, ctx));
      }
      return withCors(request, env, json({ error: "not found" }, 404));
    } catch (err) {
      console.error(err);
      return withCors(request, env, json({ error: "internal error" }, 500));
    }
  },
};

async function handleConfig(request, env) {
  const modId = new URL(request.url).searchParams.get("mod");
  const mod = findMod(env, modId);
  if (!mod) return json({ error: "unknown mod" }, 404);
  const site = getSiteConfig(env);
  return json({
    mod: { id: mod.id, display_name: mod.display_name },
    turnstile_sitekey: site.turnstileSitekey,
    max_upload_bytes: site.maxUploadBytes,
  });
}

async function handlePresign(request, env) {
  const site = getSiteConfig(env);
  const ip = request.headers.get("CF-Connecting-IP") ?? "0.0.0.0";

  const payload = await readJson(request, 8 * 1024);
  if (!payload) return json({ error: "bad request" }, 400);

  const mod = findMod(env, payload.mod);
  if (!mod) return json({ error: "unknown mod" }, 404);

  const turnstileOk = await verifyTurnstile(payload.turnstile_token, env.TURNSTILE_SECRET, ip);
  if (!turnstileOk) return json({ error: "verification failed" }, 403);

  const limit = await checkRateLimit(env.KV, ip, site.rateLimitMax, site.rateLimitWindowSeconds);
  if (!limit.allowed) return json({ error: "rate limited" }, 429, { "Retry-After": String(limit.retryAfter) });

  const declaredSize = Number(payload.size);
  if (!Number.isFinite(declaredSize) || declaredSize <= 0 || declaredSize > site.maxUploadBytes) {
    return json({ error: "invalid size" }, 413);
  }

  const submissionId = crypto.randomUUID();
  const key = objectKey(mod.id);
  const uploadUrl = await presignPut(env, key, site.presignExpirySeconds);

  await env.KV.put(
    `pending:${submissionId}`,
    JSON.stringify({ modId: mod.id, key, declaredSize }),
    { expirationTtl: PENDING_TTL_SECONDS },
  );

  return json({ submission_id: submissionId, upload_url: uploadUrl });
}

async function handleSubmit(request, env, ctx) {
  const site = getSiteConfig(env);
  const payload = await readJson(request, 64 * 1024);
  if (!payload || !payload.submission_id || typeof payload.fields !== "object") {
    return json({ error: "bad request" }, 400);
  }

  const pendingRaw = await env.KV.get(`pending:${payload.submission_id}`);
  if (!pendingRaw) return json({ error: "submission expired or unknown" }, 410);
  const pending = JSON.parse(pendingRaw);

  const mod = findMod(env, pending.modId);
  if (!mod) return json({ error: "unknown mod" }, 404);

  const fields = payload.fields;
  const check = validateFields(fields);
  if (!check.ok) return json({ error: "validation failed", details: check.errors }, 422);

  const head = await headObject(env, pending.key);
  if (!head) return json({ error: "upload not found" }, 409);
  if (head.size !== pending.declaredSize) return json({ error: "size mismatch" }, 409);

  const first3 = await getObjectRange(env, pending.key, 0, 3);
  if (!first3 || !hasSavMagic(first3)) {
    await deleteObject(env, pending.key);
    await env.KV.delete(`pending:${payload.submission_id}`);
    return json({ error: "not a valid .eu5 save" }, 415);
  }

  const saveUrl = publicUrl(env, pending.key);
  const labels = [...new Set([...site.defaultLabels, ...(mod.labels ?? [])])];
  const title = `[${mod.display_name}] ${oneLine(fields.title)}`;
  const body = renderIssueBody(fields, { saveUrl, modName: mod.display_name });

  let issue;
  try {
    issue = await createIssue(env, mod.repo, { title, body, labels });
  } catch (err) {
    // Keep the upload and pending record so a GitHub failure does not drop the report.
    console.error(err);
    return json({ error: "could not file the report; your upload was kept, please retry" }, 502);
  }

  const webhookUrl = env[mod.webhook_env];
  if (webhookUrl) {
    const embed = buildEmbed({
      modName: mod.display_name,
      title: oneLine(fields.title),
      issueUrl: issue.url,
      fields: embedFields(fields),
      saveUrl,
    });
    ctx.waitUntil(postDiscord(webhookUrl, embed).catch((err) => console.error(err)));
  }

  await env.KV.delete(`pending:${payload.submission_id}`);
  return json({ ok: true, issue_url: issue.url, issue_number: issue.number, save_url: saveUrl });
}

function objectKey(modId) {
  const now = new Date();
  const yyyy = now.getUTCFullYear();
  const mm = String(now.getUTCMonth() + 1).padStart(2, "0");
  return `saves/${modId}/${yyyy}/${mm}/${crypto.randomUUID()}.eu5`;
}

function renderIssueBody(fields, { saveUrl, modName }) {
  const lines = [
    `**Mod:** ${oneLine(modName)}`,
    `**EU5 version:** ${inlineCode(fields.eu5_version)}`,
    `**Mod version:** ${inlineCode(fields.mod_version)}`,
    "",
    "### Steps to reproduce",
    fenced(fields.steps),
    "",
    "### Expected",
    fenced(fields.expected),
    "",
    "### Actual",
    fenced(fields.actual),
    "",
    "### Other mods loaded",
    fenced(fields.other_mods),
  ];
  if (String(fields.contact ?? "").trim()) {
    lines.push("", `**Contact:** ${inlineCode(fields.contact)}`);
  }
  if (String(fields.diagnostic ?? "").trim()) {
    lines.push("", `**Diagnostic code:** ${inlineCode(fields.diagnostic)}`);
  }
  lines.push("", "---", `**Save file:** ${saveUrl}`, "", "_Filed anonymously through the bug reporter. The save link is public and is deleted after 60 days._");
  return lines.join("\n");
}

function embedFields(fields) {
  return [
    { name: "EU5 version", value: oneLine(fields.eu5_version) },
    { name: "Mod version", value: oneLine(fields.mod_version) },
    { name: "Steps", value: String(fields.steps ?? "") },
    { name: "Expected", value: String(fields.expected ?? "") },
    { name: "Actual", value: String(fields.actual ?? "") },
    { name: "Other mods", value: String(fields.other_mods ?? "") },
  ];
}

// User text is wrapped in code spans/blocks so @mentions, #refs, and links in a
// report never render or notify in the filed issue.
function fenced(text) {
  const str = String(text ?? "").trim() || "(not provided)";
  let fence = "```";
  while (str.includes(fence)) fence += "`";
  return `${fence}\n${str}\n${fence}`;
}

function inlineCode(text) {
  const str = oneLine(text) || "n/a";
  let ticks = "`";
  while (str.includes(ticks)) ticks += "`";
  const pad = str.startsWith("`") || str.endsWith("`") ? " " : "";
  return `${ticks}${pad}${str}${pad}${ticks}`;
}

function oneLine(text) {
  return String(text ?? "").replace(/\s+/g, " ").trim();
}

async function readJson(request, maxBytes) {
  const buf = await request.arrayBuffer();
  if (buf.byteLength > maxBytes) return null;
  try {
    return JSON.parse(new TextDecoder().decode(buf));
  } catch {
    return null;
  }
}

function json(obj, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...extraHeaders },
  });
}

function withCors(request, env, response) {
  const origin = request.headers.get("Origin");
  const site = env.SITE_DOMAIN ? `https://${env.SITE_DOMAIN}` : null;
  const localhost = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/;
  if (origin && (origin === site || localhost.test(origin))) {
    response.headers.set("Access-Control-Allow-Origin", origin);
    response.headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    response.headers.set("Access-Control-Allow-Headers", "Content-Type");
    response.headers.set("Vary", "Origin");
  }
  return response;
}
