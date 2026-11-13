/**
 * Noise Filter sample intake (F3).
 *
 * The app uploads short noise-only recordings here; they land in the R2 bucket under
 * incoming/<install_id>/. Nothing is trusted: size, WAV format, duration and metadata are
 * checked here, and CI screens every sample again (speech, duplicates, clipping) before a
 * sample can reach training. No IP address or other personal data is stored.
 *
 *   POST   /v1/samples                 body: WAV (48 kHz, mono, 16-bit PCM, 2-10 s)
 *                                      header X-NF-Meta: JSON {install_id, category, app_version, os, consent,
 *                                      source: "mic" (Learn noise recording, default) | "file" (user's own file)}
 *   DELETE /v1/samples?install_id=...  removes every sample of that installation
 *   GET    /v1/health
 *   /review, /v1/review/*              developer review of screened samples (see review.js)
 */
import { handleReview } from "./review.js";

export const MAX_BYTES = 2 * 1024 * 1024;
export const SAMPLE_RATE = 48000;
export const MIN_SECONDS = 2;
export const MAX_SECONDS = 10;
export const CATEGORIES = ["fan_ac", "traffic", "keyboard", "crowd", "machine", "rain_wind", "other"];
export const CONSENT = "cc0-v1";
export const PREFIXES = ["incoming/", "review/", "accepted/", "rejected/"];
export const SOURCES = ["mic", "file"];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const VERSION = /^\d{1,3}\.\d{1,3}\.\d{1,3}([.-][0-9A-Za-z.]{1,20})?$/;

const json = (status, body) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "access-control-allow-origin": "*" },
  });

/** Parse a RIFF/WAVE header. Returns {rate, channels, bits, format, dataBytes} or throws. */
export function parseWav(buf) {
  const v = new DataView(buf);
  const tag = (o) => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3));
  if (buf.byteLength < 44 || tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a WAV file");
  let o = 12, fmt = null;
  while (o + 8 <= buf.byteLength) {
    const id = tag(o), size = v.getUint32(o + 4, true);
    if (id === "fmt ") {
      if (size < 16 || o + 8 + size > buf.byteLength) throw new Error("bad fmt chunk");
      fmt = { format: v.getUint16(o + 8, true), channels: v.getUint16(o + 10, true),
              rate: v.getUint32(o + 12, true), bits: v.getUint16(o + 22, true) };
    } else if (id === "data") {
      if (!fmt) throw new Error("data before fmt");
      return { ...fmt, dataBytes: Math.min(size, buf.byteLength - o - 8) };
    }
    o += 8 + size + (size & 1);
  }
  throw new Error("no data chunk");
}

export function checkMeta(raw) {
  let m;
  try { m = JSON.parse(raw || ""); } catch { throw new Error("X-NF-Meta is not JSON"); }
  if (!m || typeof m !== "object") throw new Error("X-NF-Meta must be an object");
  if (!UUID.test(String(m.install_id))) throw new Error("install_id must be a random UUID v4");
  if (!CATEGORIES.includes(m.category)) throw new Error("unknown category");
  if (!VERSION.test(String(m.app_version))) throw new Error("bad app_version");
  if (!["windows", "android", "linux", "macos", "ios"].includes(m.os)) throw new Error("bad os");
  if (m.consent !== CONSENT) throw new Error("consent missing");
  const source = m.source ?? "mic";
  if (!SOURCES.includes(source)) throw new Error("bad source");
  return { install_id: m.install_id, category: m.category, app_version: m.app_version, os: m.os, consent: m.consent, source };
}

async function upload(request, env) {
  const len = Number(request.headers.get("content-length") || 0);
  if (len > MAX_BYTES) return json(413, { ok: false, error: "too large" });
  let meta;
  try { meta = checkMeta(request.headers.get("x-nf-meta")); } catch (e) { return json(400, { ok: false, error: e.message }); }

  if (env.UPLOAD_LIMIT) {   // Cloudflare rate-limiting binding (optional in tests / local dev)
    const { success } = await env.UPLOAD_LIMIT.limit({ key: meta.install_id });
    if (!success) return json(429, { ok: false, error: "too many uploads, try again tomorrow" });
  }

  const body = await request.arrayBuffer();
  if (body.byteLength > MAX_BYTES) return json(413, { ok: false, error: "too large" });
  let wav;
  try { wav = parseWav(body); } catch (e) { return json(400, { ok: false, error: e.message }); }
  if (wav.format !== 1 || wav.channels !== 1 || wav.rate !== SAMPLE_RATE || wav.bits !== 16)
    return json(400, { ok: false, error: "need 48 kHz mono 16-bit PCM" });
  const seconds = wav.dataBytes / 2 / SAMPLE_RATE;
  if (seconds < MIN_SECONDS || seconds > MAX_SECONDS) return json(400, { ok: false, error: "need 2-10 seconds" });

  const id = `${new Date().toISOString().slice(0, 10)}-${crypto.randomUUID()}`;
  const key = `incoming/${meta.install_id}/${id}.wav`;
  await env.SAMPLES.put(key, body, {
    httpMetadata: { contentType: "audio/wav" },
    customMetadata: { ...meta, seconds: seconds.toFixed(2) },
  });
  return json(201, { ok: true, id });
}

async function remove(url, env) {
  const installId = url.searchParams.get("install_id") || "";
  if (!UUID.test(installId)) return json(400, { ok: false, error: "install_id must be a UUID v4" });
  let deleted = 0;
  for (const p of PREFIXES) {
    let cursor;
    do {
      const page = await env.SAMPLES.list({ prefix: `${p}${installId}/`, cursor });
      const keys = page.objects.map((o) => o.key);
      if (keys.length) { await env.SAMPLES.delete(keys); deleted += keys.length; }
      cursor = page.truncated ? page.cursor : undefined;
    } while (cursor);
  }
  return json(200, { ok: true, deleted });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/v1/health") return json(200, { ok: true });
    const review = await handleReview(request, env, url);
    if (review) return review;
    if (url.pathname === "/v1/samples") {
      if (request.method === "POST") return upload(request, env);
      if (request.method === "DELETE") return remove(url, env);
      return json(405, { ok: false, error: "method not allowed" });
    }
    return json(404, { ok: false, error: "not found" });
  },
};
