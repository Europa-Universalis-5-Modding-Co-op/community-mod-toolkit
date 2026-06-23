// R2 access: a SigV4-presigned PUT for the direct browser upload, plus the
// finalize-time size and magic checks through the bucket binding.

import { AwsClient } from "aws4fetch";

export async function presignPut(env, key, expirySeconds) {
  const client = new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    service: "s3",
    region: "auto",
  });
  const endpoint = `https://${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${env.R2_BUCKET}/${encodeKey(key)}`;
  const url = new URL(endpoint);
  url.searchParams.set("X-Amz-Expires", String(expirySeconds));
  const signed = await client.sign(url.toString(), { method: "PUT", aws: { signQuery: true } });
  return signed.url;
}

export function headObject(env, key) {
  return env.SAVES_BUCKET.head(key);
}

export async function getObjectRange(env, key, offset, length) {
  const obj = await env.SAVES_BUCKET.get(key, { range: { offset, length } });
  if (!obj) return null;
  return new Uint8Array(await obj.arrayBuffer());
}

export function deleteObject(env, key) {
  return env.SAVES_BUCKET.delete(key);
}

export function publicUrl(env, key) {
  return `https://${env.SAVES_DOMAIN}/${encodeKey(key)}`;
}

function encodeKey(key) {
  return key.split("/").map(encodeURIComponent).join("/");
}
