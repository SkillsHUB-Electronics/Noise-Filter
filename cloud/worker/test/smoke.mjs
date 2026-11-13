// Post-deploy smoke test: upload a 2 s test tone, then delete it again.  node test/smoke.mjs <url>
const url = process.argv[2];
const id = crypto.randomUUID();
const n = 48000 * 2, b = new ArrayBuffer(44 + n * 2), v = new DataView(b);
const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt "); v.setUint32(16, 16, true);
v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 48000, true); v.setUint32(28, 96000, true);
v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
for (let i = 0; i < n; i++) v.setInt16(44 + 2 * i, Math.round(300 * Math.sin(i * 0.07)), true);
const meta = { install_id: id, category: "other", app_version: "0.0.0", os: "linux", consent: "cc0-v1" };
const up = await fetch(`${url}/v1/samples`, { method: "POST", body: b,
  headers: { "content-type": "audio/wav", "x-nf-meta": JSON.stringify(meta) } });
console.log("upload", up.status, await up.text());
const del = await fetch(`${url}/v1/samples?install_id=${id}`, { method: "DELETE" });
const res = await del.json();
console.log("delete", del.status, JSON.stringify(res));
if (up.status !== 201 || res.deleted !== 1) process.exit(1);
