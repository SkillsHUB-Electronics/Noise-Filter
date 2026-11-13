/**
 * Developer review of contributed noise samples.
 *
 * CI screens incoming/ automatically and moves samples that pass into review/. Nothing reaches
 * training until the developer listens to it here and accepts it (accepted/). Rejected samples
 * go to rejected/ and are deleted by CI after 30 days.
 *
 *   GET  /review                          the review page (HTML; asks for the password)
 *   GET  /review/logo.png                 the app logo used by the page
 *   GET  /v1/review/list?state=review     samples in one state (review|accepted|rejected|incoming)
 *   GET  /v1/review/audio?key=...         one sample's WAV
 *   POST /v1/review/decide                {keys: [...], decision: "accept"|"reject"|"review"}
 *   GET  /v1/review/stats                 number of samples in each state
 *
 * Every /v1/review route needs "Authorization: Bearer <REVIEW_PASSWORD>". The password is a
 * Worker secret (set by CI from the GitHub secret REVIEW_PASSWORD). Without it the review
 * routes are switched off.
 */
import { REVIEW_PAGE } from "./review_page.js";
import { LOGO_PNG_BASE64 } from "./review_logo.js";

const LOGO = Uint8Array.from(atob(LOGO_PNG_BASE64), (c) => c.charCodeAt(0));

export const STATES = ["review", "accepted", "rejected", "incoming"];
const DEST = { accept: "accepted", reject: "rejected", review: "review" };
const KEY = /^(review|accepted|rejected|incoming)\/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\/[0-9A-Za-z._-]{1,80}\.wav$/;
const MAX_BATCH = 100;

const json = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

async function digest(s) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
}

/** Constant-time password check (compares SHA-256 digests byte by byte). */
export async function authorized(request, env) {
  const pw = env.REVIEW_PASSWORD;
  if (!pw) return false;
  const m = /^Bearer (.+)$/.exec(request.headers.get("authorization") || "");
  if (!m) return false;
  const [a, b] = [await digest(m[1]), await digest(pw)];
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

export const validKey = (k) => typeof k === "string" && KEY.test(k);

async function list(url, env) {
  const state = url.searchParams.get("state") || "review";
  if (!STATES.includes(state)) return json(400, { ok: false, error: "unknown state" });
  const page = await env.SAMPLES.list({
    prefix: `${state}/`, cursor: url.searchParams.get("cursor") || undefined, limit: 200,
    include: ["customMetadata"],
  });
  const items = page.objects.map((o) => ({
    key: o.key, size: o.size, uploaded: o.uploaded, meta: o.customMetadata || {},
  }));
  return json(200, { ok: true, items, cursor: page.truncated ? page.cursor : null });
}

async function audio(url, env) {
  const key = url.searchParams.get("key");
  if (!validKey(key)) return json(400, { ok: false, error: "bad key" });
  const obj = await env.SAMPLES.get(key);
  if (!obj) return json(404, { ok: false, error: "not found" });
  return new Response(obj.body, { headers: { "content-type": "audio/wav", "cache-control": "private, max-age=3600" } });
}

/** Move one object to another state, keeping its metadata and recording the decision. */
export async function move(env, key, decision, now = new Date()) {
  const dest = `${DEST[decision]}/${key.slice(key.indexOf("/") + 1)}`;
  if (dest === key) return dest;
  const obj = await env.SAMPLES.get(key);
  if (!obj) throw new Error(`not found: ${key}`);
  const meta = { ...(obj.customMetadata || {}) };
  if (decision === "review") delete meta.reviewed;
  else meta.reviewed = `${decision}ed ${now.toISOString().slice(0, 19)}Z`;
  if (decision === "reject" && !meta.reason?.startsWith("manual")) meta.reason = `manual (was: ${meta.reason || "-"})`;
  await env.SAMPLES.put(dest, await obj.arrayBuffer(), {
    httpMetadata: { contentType: "audio/wav" }, customMetadata: meta,
  });
  await env.SAMPLES.delete(key);
  return dest;
}

async function decide(request, env) {
  let body;
  try { body = await request.json(); } catch { return json(400, { ok: false, error: "body must be JSON" }); }
  const keys = [].concat(body?.keys || []);
  if (!DEST[body?.decision]) return json(400, { ok: false, error: "decision must be accept, reject or review" });
  if (!keys.length || keys.length > MAX_BATCH) return json(400, { ok: false, error: `send 1-${MAX_BATCH} keys` });
  if (!keys.every(validKey)) return json(400, { ok: false, error: "bad key" });
  const moved = {}, errors = {};
  for (const k of keys) {
    try { moved[k] = await move(env, k, body.decision); } catch (e) { errors[k] = e.message; }
  }
  return json(200, { ok: !Object.keys(errors).length, moved, errors });
}

async function stats(env) {
  const counts = {};
  for (const s of STATES) {
    let n = 0, cursor;
    do {
      const page = await env.SAMPLES.list({ prefix: `${s}/`, cursor, limit: 1000 });
      n += page.objects.length;
      cursor = page.truncated ? page.cursor : undefined;
    } while (cursor);
    counts[s] = n;
  }
  return json(200, { ok: true, counts });
}

/** Returns a Response for review routes, or null when the path is not a review route. */
export async function handleReview(request, env, url) {
  if (url.pathname === "/review" || url.pathname === "/review/") {
    return new Response(REVIEW_PAGE, {
      headers: {
        "content-type": "text/html; charset=utf-8", "cache-control": "no-store",
        "x-frame-options": "DENY", "referrer-policy": "no-referrer",
        "content-security-policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self' blob:; img-src 'self' data:",
      },
    });
  }
  if (url.pathname === "/review/logo.png") {
    return new Response(LOGO, { headers: { "content-type": "image/png", "cache-control": "public, max-age=86400" } });
  }
  if (!url.pathname.startsWith("/v1/review/")) return null;
  if (!env.REVIEW_PASSWORD || env.REVIEW_PASSWORD.length < 12)
    return json(503, { ok: false, error: "review is not configured (REVIEW_PASSWORD secret missing or shorter than 12 characters)" });
  if (!(await authorized(request, env))) {
    // at most 5 wrong passwords a minute in total: guessing a long password this way is hopeless
    if (env.UPLOAD_LIMIT && !(await env.UPLOAD_LIMIT.limit({ key: "review-login" })).success)
      return json(429, { ok: false, error: "too many wrong passwords, wait a minute" });
    return json(401, { ok: false, error: "wrong password" });
  }
  const route = url.pathname.slice("/v1/review/".length);
  if (request.method === "GET" && route === "list") return list(url, env);
  if (request.method === "GET" && route === "audio") return audio(url, env);
  if (request.method === "GET" && route === "stats") return stats(env);
  if (request.method === "POST" && route === "decide") return decide(request, env);
  return json(404, { ok: false, error: "not found" });
}
