import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { parseWav } from "../src/index.js";

const ID = "3f2b8c1e-9a4d-4e6f-8b2a-1c3d5e7f9a0b";
const META = { install_id: ID, category: "fan_ac", app_version: "0.4.0", os: "windows", consent: "cc0-v1" };

function wav(seconds, { rate = 48000, channels = 1, bits = 16 } = {}) {
  const n = Math.round(seconds * rate) * channels * (bits / 8);
  const b = new ArrayBuffer(44 + n), v = new DataView(b);
  const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); v.setUint32(4, 36 + n, true); w(8, "WAVE");
  w(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, channels, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * channels * bits / 8, true);
  v.setUint16(32, channels * bits / 8, true); v.setUint16(34, bits, true);
  w(36, "data"); v.setUint32(40, n, true);
  return b;
}

class FakeBucket {
  constructor() { this.objects = new Map(); }
  async put(key, body, opts) { this.objects.set(key, { body, opts }); }
  async list({ prefix }) {
    return { objects: [...this.objects.keys()].filter((k) => k.startsWith(prefix)).map((key) => ({ key })), truncated: false };
  }
  async delete(keys) { for (const k of [].concat(keys)) this.objects.delete(k); }
}

const post = (body, meta = META) => new Request("https://x/v1/samples", {
  method: "POST", body, headers: { "x-nf-meta": JSON.stringify(meta), "content-type": "audio/wav" },
});

test("parses a WAV header", () => {
  const h = parseWav(wav(3));
  assert.deepEqual([h.rate, h.channels, h.bits, h.format, h.dataBytes], [48000, 1, 16, 1, 3 * 48000 * 2]);
  assert.throws(() => parseWav(new ArrayBuffer(100)), /not a WAV/);
});

test("accepts a valid sample and stores it under incoming/<install_id>/", async () => {
  const env = { SAMPLES: new FakeBucket() };
  const r = await worker.fetch(post(wav(5)), env);
  assert.equal(r.status, 201);
  const [key] = env.SAMPLES.objects.keys();
  assert.match(key, new RegExp(`^incoming/${ID}/\\d{4}-\\d{2}-\\d{2}-[0-9a-f-]{36}\\.wav$`));
  const meta = env.SAMPLES.objects.get(key).opts.customMetadata;
  assert.equal(meta.category, "fan_ac");
  assert.equal(meta.seconds, "5.00");
});

test("rejects bad format, length, metadata and consent", async () => {
  const env = { SAMPLES: new FakeBucket() };
  const cases = [
    [post(wav(5, { rate: 44100 })), 400],
    [post(wav(5, { channels: 2 })), 400],
    [post(wav(1)), 400],
    [post(wav(11)), 400],
    [post(wav(5), { ...META, consent: undefined }), 400],
    [post(wav(5), { ...META, install_id: "not-a-uuid" }), 400],
    [post(wav(5), { ...META, category: "speech" }), 400],
    [post(new ArrayBuffer(3 * 1024 * 1024)), 413],
  ];
  for (const [req, status] of cases) assert.equal((await worker.fetch(req, env)).status, status);
  assert.equal(env.SAMPLES.objects.size, 0);
});

test("rate limit is applied per installation", async () => {
  const env = { SAMPLES: new FakeBucket(), UPLOAD_LIMIT: { limit: async ({ key }) => ({ success: key !== ID }) } };
  assert.equal((await worker.fetch(post(wav(5)), env)).status, 429);
});

test("delete removes every sample of one installation only", async () => {
  const env = { SAMPLES: new FakeBucket() };
  await worker.fetch(post(wav(3)), env);
  await worker.fetch(post(wav(3)), env);
  env.SAMPLES.objects.set(`accepted/${ID}/a.wav`, {});
  env.SAMPLES.objects.set("accepted/11111111-1111-4111-8111-111111111111/b.wav", {});
  const r = await worker.fetch(new Request(`https://x/v1/samples?install_id=${ID}`, { method: "DELETE" }), env);
  assert.deepEqual(await r.json(), { ok: true, deleted: 3 });
  assert.equal(env.SAMPLES.objects.size, 1);
});

test("health and unknown routes", async () => {
  assert.equal((await worker.fetch(new Request("https://x/v1/health"), {})).status, 200);
  assert.equal((await worker.fetch(new Request("https://x/nope"), {})).status, 404);
});
