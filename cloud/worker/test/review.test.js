import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { REVIEW_PAGE } from "../src/review_page.js";

const ID = "3f2b8c1e-9a4d-4e6f-8b2a-1c3d5e7f9a0b";
const PW = "correct horse battery staple";

class Bucket {
  constructor() { this.o = new Map(); }
  async put(key, body, opts = {}) { this.o.set(key, { body, meta: opts.customMetadata || {} }); }
  async get(key) {
    const v = this.o.get(key);
    if (!v) return null;
    return { customMetadata: v.meta, body: v.body, arrayBuffer: async () => v.body };
  }
  async list({ prefix, include }) {
    const objects = [...this.o.keys()].filter((k) => k.startsWith(prefix)).sort().map((key) => ({
      key, size: 4, uploaded: "2026-11-13T00:00:00Z",
      ...(include?.includes("customMetadata") ? { customMetadata: this.o.get(key).meta } : {}),
    }));
    return { objects, truncated: false };
  }
  async delete(keys) { for (const k of [].concat(keys)) this.o.delete(k); }
}

const env = () => {
  const b = new Bucket();
  b.o.set(`review/${ID}/2026-11-13-a.wav`, { body: new ArrayBuffer(4), meta: { category: "fan_ac", reason: "ok" } });
  b.o.set(`review/${ID}/2026-11-13-b.wav`, { body: new ArrayBuffer(4), meta: { category: "other", reason: "ok" } });
  b.o.set(`rejected/${ID}/2026-11-13-c.wav`, { body: new ArrayBuffer(4), meta: { reason: "speech" } });
  return { SAMPLES: b, REVIEW_PASSWORD: PW };
};
const req = (path, { pw = PW, ...opts } = {}) =>
  new Request(`https://x${path}`, { ...opts, headers: { authorization: `Bearer ${pw}`, ...(opts.headers || {}) } });
const decide = (keys, decision, e) => worker.fetch(req("/v1/review/decide", {
  method: "POST", body: JSON.stringify({ keys, decision }), headers: { "content-type": "application/json" } }), e);

test("review page is served without a password, the API is not", async () => {
  const e = env();
  const page = await worker.fetch(new Request("https://x/review"), e);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /Review sampel noise/);
  assert.match(page.headers.get("content-security-policy"), /default-src 'self'/);
  assert.equal((await worker.fetch(req("/v1/review/stats", { pw: "wrong password!!" }), e)).status, 401);
  assert.equal((await worker.fetch(new Request("https://x/v1/review/stats"), e)).status, 401);
  assert.equal((await worker.fetch(req("/v1/review/stats"), { ...e, REVIEW_PASSWORD: undefined })).status, 503);
  assert.equal((await worker.fetch(req("/v1/review/stats", { pw: "short" }), { ...e, REVIEW_PASSWORD: "short" })).status, 503);
});

test("wrong passwords are rate limited", async () => {
  const e = { ...env(), UPLOAD_LIMIT: { limit: async ({ key }) => ({ success: key !== "review-login" }) } };
  assert.equal((await worker.fetch(req("/v1/review/stats", { pw: "nope nope nope" }), e)).status, 429);
  assert.equal((await worker.fetch(req("/v1/review/stats"), e)).status, 200);
});

test("lists samples with metadata and counts every state", async () => {
  const e = env();
  const l = await (await worker.fetch(req("/v1/review/list?state=review"), e)).json();
  assert.deepEqual(l.items.map((i) => i.meta.category), ["fan_ac", "other"]);
  const s = await (await worker.fetch(req("/v1/review/stats"), e)).json();
  assert.deepEqual(s.counts, { review: 2, accepted: 0, rejected: 1, incoming: 0 });
  assert.equal((await worker.fetch(req("/v1/review/list?state=secret"), e)).status, 400);
});

test("serves audio only for valid sample keys", async () => {
  const e = env();
  const r = await worker.fetch(req(`/v1/review/audio?key=review/${ID}/2026-11-13-a.wav`), e);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("content-type"), "audio/wav");
  for (const k of ["../x.wav", `other/${ID}/a.wav`, `review/${ID}/../../a.wav`, `review/not-uuid/a.wav`])
    assert.equal((await worker.fetch(req(`/v1/review/audio?key=${encodeURIComponent(k)}`), e)).status, 400);
  assert.equal((await worker.fetch(req(`/v1/review/audio?key=review/${ID}/zzz.wav`), e)).status, 404);
});

test("accept, reject and send back move samples and record the decision", async () => {
  const e = env(), o = e.SAMPLES.o;
  let j = await (await decide([`review/${ID}/2026-11-13-a.wav`], "accept", e)).json();
  assert.ok(j.ok);
  assert.ok(o.has(`accepted/${ID}/2026-11-13-a.wav`) && !o.has(`review/${ID}/2026-11-13-a.wav`));
  assert.match(o.get(`accepted/${ID}/2026-11-13-a.wav`).meta.reviewed, /^accepted 20/);
  assert.equal(o.get(`accepted/${ID}/2026-11-13-a.wav`).meta.category, "fan_ac");

  await decide([`review/${ID}/2026-11-13-b.wav`], "reject", e);
  assert.equal(o.get(`rejected/${ID}/2026-11-13-b.wav`).meta.reason, "manual (was: ok)");

  // a false positive of the automatic check can still be accepted
  await decide([`rejected/${ID}/2026-11-13-c.wav`], "accept", e);
  assert.ok(o.has(`accepted/${ID}/2026-11-13-c.wav`));

  await decide([`accepted/${ID}/2026-11-13-a.wav`], "review", e);
  assert.equal(o.get(`review/${ID}/2026-11-13-a.wav`).meta.reviewed, undefined);

  j = await (await decide([`review/${ID}/missing.wav`], "accept", e)).json();
  assert.equal(j.ok, false);
  assert.equal((await decide(["../../etc.wav"], "accept", e)).status, 400);
  assert.equal((await decide([`review/${ID}/2026-11-13-a.wav`], "delete", e)).status, 400);
});

test("the page script has no syntax errors", () => {
  const js = REVIEW_PAGE.split("<script>")[1].split("</script>")[0];
  assert.doesNotThrow(() => new Function(js));
});
