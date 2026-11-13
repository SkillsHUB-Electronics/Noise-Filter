// The developer review page served at /review. Plain HTML + JS, no dependencies.
// (Kept as a string so the Worker stays a single bundle; the page uses no backticks or "${".)
export const REVIEW_PAGE = String.raw`<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Review sampel noise</title>
<style>
:root { --bg:#f6f7f9; --card:#fff; --ink:#1b1f24; --mute:#667085; --line:#e3e6ea; --acc:#2563eb;
        --ok:#15803d; --okbg:#e7f6ec; --bad:#b42318; --badbg:#fdecea; --sel:#eaf1ff; }
@media (prefers-color-scheme: dark) { :root { --bg:#111418; --card:#1a1e24; --ink:#e7e9ec; --mute:#98a2b3;
        --line:#2b313a; --acc:#6aa0ff; --ok:#4ade80; --okbg:#173322; --bad:#f87171; --badbg:#3a1a1a; --sel:#1d2a44; }
        button.ok, button.bad { color:#111 !important } }
* { box-sizing:border-box }
body { margin:0; font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink) }
header { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; padding:12px 16px; border-bottom:1px solid var(--line); background:var(--card) }
h1 { font-size:16px; margin:0 }
.tabs { display:flex; gap:4px; flex-wrap:wrap }
.tabs button { border:1px solid var(--line); background:transparent; color:var(--ink); border-radius:999px; padding:4px 12px; cursor:pointer }
.tabs button.on { background:var(--acc); border-color:var(--acc); color:#fff }
main { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.1fr); gap:16px; padding:16px; max-width:1400px; margin:0 auto }
@media (max-width:900px) { main { grid-template-columns:1fr } #player { order:-1 } }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px }
#list { overflow:auto; max-height:calc(100vh - 110px) }
@media (max-width:900px) { #list { max-height:none } }
table { width:100%; border-collapse:collapse }
th, td { padding:7px 10px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap }
th { position:sticky; top:0; background:var(--card); font-weight:600; font-size:12px; color:var(--mute) }
tr.row { cursor:pointer } tr.row:hover { background:var(--sel) } tr.row.cur { background:var(--sel); box-shadow:inset 3px 0 var(--acc) }
.tag { display:inline-block; font-size:12px; padding:1px 7px; border-radius:6px; background:var(--line) }
.tag.ok { background:var(--okbg); color:var(--ok) } .tag.bad { background:var(--badbg); color:var(--bad) }
.mute { color:var(--mute) }
#player { padding:16px; position:sticky; top:16px; align-self:start }
canvas { width:100%; height:260px; display:block; border-radius:6px; background:#000 }
#wave { height:60px; margin-top:6px; background:transparent }
.meta { display:grid; grid-template-columns:auto 1fr; gap:3px 12px; margin:12px 0; font-size:13px }
.btns { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px }
button.b { border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:8px; padding:8px 14px; cursor:pointer; font:inherit }
button.b:disabled { opacity:.45; cursor:default }
button.ok { background:var(--ok); border-color:var(--ok); color:#fff } button.bad { background:var(--bad); border-color:var(--bad); color:#fff }
kbd { font:11px ui-monospace,monospace; border:1px solid var(--line); border-bottom-width:2px; border-radius:4px; padding:0 4px; margin-left:4px; opacity:.8 }
#bulk { display:flex; gap:8px; align-items:center; padding:8px 10px; border-bottom:1px solid var(--line); flex-wrap:wrap }
#login { max-width:380px; margin:12vh auto; padding:24px }
#login input { width:100%; padding:9px; margin:10px 0; border:1px solid var(--line); border-radius:8px; background:var(--bg); color:var(--ink); font:inherit }
#msg { margin-left:auto; font-size:13px }
.empty { padding:40px; text-align:center; color:var(--mute) }
.hint { font-size:12px; color:var(--mute); margin-top:12px }
</style>
</head>
<body>
<div id="login" class="card" hidden>
  <h1>Review sampel noise</h1>
  <p class="mute">Masukkan password review (GitHub Secret <b>REVIEW_PASSWORD</b>).</p>
  <form id="loginf"><input id="pw" type="password" autocomplete="current-password" placeholder="Password" required>
  <label><input id="remember" type="checkbox"> Ingat di perangkat ini</label><br><br>
  <button class="b ok" type="submit">Masuk</button> <span id="loginerr" style="color:var(--bad)"></span></form>
</div>
<div id="app" hidden>
<header>
  <h1>Review sampel noise</h1>
  <div class="tabs" id="tabs"></div>
  <label class="mute"><input type="checkbox" id="autoplay" checked> Putar otomatis</label>
  <span id="msg" class="mute"></span>
  <button class="b" id="logout">Keluar</button>
</header>
<main>
  <section class="card" id="list"></section>
  <section class="card" id="player">
    <div id="pempty" class="empty">Pilih sampel di daftar.</div>
    <div id="pbody" hidden>
      <canvas id="spec" width="1024" height="260"></canvas>
      <canvas id="wave" width="1024" height="60"></canvas>
      <div class="btns">
        <button class="b" id="play">▶ Putar<kbd>Spasi</kbd></button>
        <button class="b ok" id="acc">Terima<kbd>A</kbd></button>
        <button class="b bad" id="rej">Tolak<kbd>R</kbd></button>
        <button class="b" id="back">Kembalikan ke antrean<kbd>U</kbd></button>
      </div>
      <div class="meta" id="meta"></div>
      <div class="hint">Spektrogram 0–16 kHz. Noise yang bagus biasanya rata dan stabil (kipas, AC, hujan, lalu lintas).
        Tolak musik, suara TV/orang, rekaman kosong atau rusak, dan apa pun yang bukan noise ruangan.
        Navigasi: <kbd>↓</kbd>/<kbd>J</kbd> berikutnya, <kbd>↑</kbd>/<kbd>K</kbd> sebelumnya.</div>
    </div>
  </section>
</main>
</div>
<script>
"use strict";
var STATES = [["review","Antrean"],["accepted","Diterima"],["rejected","Ditolak"],["incoming","Belum dicek"]];
var CAT = {fan_ac:"Kipas / AC", traffic:"Lalu lintas", keyboard:"Keyboard / klik", crowd:"Keramaian",
           machine:"Mesin / bengkel", rain_wind:"Hujan / angin", other:"Lainnya"};
var pw = sessionStorage.getItem("nfpw") || localStorage.getItem("nfpw") || "";
var state = "review", items = [], cursor = null, cur = -1, picked = {}, counts = {};
var audio = new Audio(), actx = null, cache = {};
var $ = function (id) { return document.getElementById(id); };

function api(path, opts) {
  opts = opts || {};
  opts.headers = Object.assign({authorization: "Bearer " + pw}, opts.headers || {});
  return fetch(path, opts).then(function (r) {
    if (r.status === 401 || r.status === 429) { showLogin(r.status === 429 ? "Terlalu banyak percobaan, tunggu 1 menit." : "Password salah."); throw new Error("auth"); }
    return r;
  });
}
function showLogin(err) { $("app").hidden = true; $("login").hidden = false; $("loginerr").textContent = err || ""; $("pw").focus(); }
$("loginf").onsubmit = function (e) {
  e.preventDefault(); pw = $("pw").value;
  sessionStorage.setItem("nfpw", pw); if ($("remember").checked) localStorage.setItem("nfpw", pw);
  start();
};
$("logout").onclick = function () { sessionStorage.removeItem("nfpw"); localStorage.removeItem("nfpw"); pw = ""; showLogin(); };
function msg(t) { $("msg").textContent = t; }

function start() {
  api("/v1/review/stats").then(function (r) { return r.json(); }).then(function (j) {
    if (!j.ok) { showLogin(j.error); return; }
    $("login").hidden = true; $("app").hidden = false; counts = j.counts; tabs(); load(true);
  }).catch(function () {});
}
function tabs() {
  $("tabs").innerHTML = "";
  STATES.forEach(function (s) {
    var b = document.createElement("button");
    b.textContent = s[1] + " (" + (counts[s[0]] || 0) + ")"; b.className = s[0] === state ? "on" : "";
    b.onclick = function () { state = s[0]; tabs(); load(true); };
    $("tabs").appendChild(b);
  });
}
function refreshCounts() { api("/v1/review/stats").then(function (r) { return r.json(); }).then(function (j) { if (j.ok) { counts = j.counts; tabs(); } }).catch(function () {}); }

function load(reset) {
  if (reset) { items = []; cursor = null; cur = -1; picked = {}; }
  var q = "/v1/review/list?state=" + state + (cursor ? "&cursor=" + encodeURIComponent(cursor) : "");
  msg("Memuat…");
  api(q).then(function (r) { return r.json(); }).then(function (j) {
    items = items.concat(j.items); cursor = j.cursor; msg(""); render();
    if (reset && items.length) select(0);
    if (!items.length) showEmpty();
  }).catch(function () {});
}

function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return "&#" + c.charCodeAt(0) + ";"; }); }
function shortId(k) { return k.split("/")[1].slice(0, 8); }
function when(k) { var f = k.split("/")[2]; return f.slice(0, 10); }
function verdict(m) {
  if (!m.reason) return '<span class="tag">belum dicek</span>';
  var ok = m.reason === "ok";
  return '<span class="tag ' + (ok ? "ok" : "bad") + '">' + esc(ok ? "lolos" : m.reason) + "</span>";
}

function render() {
  var h = '<div id="bulk"><label><input type="checkbox" id="all"> Pilih semua</label>' +
    '<button class="b ok" id="bacc" disabled>Terima terpilih</button><button class="b bad" id="brej" disabled>Tolak terpilih</button>' +
    '<span class="mute" id="npick"></span></div>';
  if (!items.length) { $("list").innerHTML = h + '<div class="empty">Tidak ada sampel di sini.</div>'; wireBulk(); return; }
  h += "<table><thead><tr><th></th><th>Jenis</th><th>Durasi</th><th>Sumber</th><th>Tanggal</th><th>Cek otomatis</th><th>Instalasi</th></tr></thead><tbody>";
  items.forEach(function (it, i) {
    var m = it.meta || {};
    h += '<tr class="row' + (i === cur ? " cur" : "") + '" data-i="' + i + '">' +
      '<td><input type="checkbox" data-k="' + i + '"' + (picked[it.key] ? " checked" : "") + "></td>" +
      "<td>" + esc(CAT[m.category] || m.category || "?") + "</td>" +
      "<td>" + esc(m.seconds ? (+m.seconds).toFixed(1) + " s" : "?") + "</td>" +
      "<td>" + esc(m.source === "file" ? "file" : "mikrofon") + "</td>" +
      "<td>" + esc(when(it.key)) + "</td><td>" + verdict(m) + "</td>" +
      '<td class="mute">' + esc(shortId(it.key)) + "</td></tr>";
  });
  h += "</tbody></table>";
  if (cursor) h += '<div class="empty"><button class="b" id="more">Muat lagi</button></div>';
  $("list").innerHTML = h;
  Array.prototype.forEach.call(document.querySelectorAll("tr.row"), function (tr) {
    tr.onclick = function (e) { if (e.target.type !== "checkbox") select(+tr.dataset.i); };
  });
  Array.prototype.forEach.call(document.querySelectorAll("input[data-k]"), function (cb) {
    cb.onchange = function () { var k = items[+cb.dataset.k].key; if (cb.checked) picked[k] = 1; else delete picked[k]; pickInfo(); };
  });
  if ($("more")) $("more").onclick = function () { load(false); };
  wireBulk();
}
function wireBulk() {
  $("all").onchange = function () { picked = {}; if ($("all").checked) items.forEach(function (it) { picked[it.key] = 1; }); render(); };
  $("bacc").onclick = function () { decide(Object.keys(picked), "accept"); };
  $("brej").onclick = function () { decide(Object.keys(picked), "reject"); };
  $("bacc").hidden = state === "accepted"; $("brej").hidden = state === "rejected";
  pickInfo();
}
function pickInfo() {
  var n = Object.keys(picked).length;
  $("npick").textContent = n ? n + " dipilih" : ""; $("bacc").disabled = $("brej").disabled = !n;
  $("all").checked = n > 0 && n === items.length;
}

function showEmpty() { $("pbody").hidden = true; $("pempty").hidden = false; audio.pause(); }
function select(i) {
  if (i < 0 || i >= items.length) return;
  cur = i; var it = items[i], m = it.meta || {};
  Array.prototype.forEach.call(document.querySelectorAll("tr.row"), function (tr) { tr.classList.toggle("cur", +tr.dataset.i === i); });
  var row = document.querySelector('tr.row[data-i="' + i + '"]'); if (row) row.scrollIntoView({block: "nearest"});
  $("pempty").hidden = true; $("pbody").hidden = false;
  $("acc").disabled = state === "accepted"; $("rej").disabled = state === "rejected"; $("back").disabled = state === "review";
  var rows = [["Jenis", CAT[m.category] || m.category], ["Durasi", m.seconds ? m.seconds + " s" : "?"],
    ["Sumber", m.source === "file" ? "file yang diunggah pengguna" : "rekaman mikrofon (Pelajari noise)"],
    ["Cek otomatis", m.reason || "belum dicek"], ["Keputusan", m.reviewed || "-"],
    ["Aplikasi", (m.app_version || "?") + " / " + (m.os || "?")], ["Instalasi", it.key.split("/")[1]], ["File", it.key]];
  $("meta").innerHTML = rows.map(function (r) { return '<span class="mute">' + esc(r[0]) + "</span><span>" + esc(r[1]) + "</span>"; }).join("");
  clearCanvas();
  getAudio(it.key).then(function (d) {
    if (items[cur] !== it) return;
    audio.src = d.url; drawSpec(d.buf);
    if ($("autoplay").checked) audio.play().catch(function () {});
  }).catch(function (e) { if (e.message !== "auth") msg("Gagal memuat audio"); });
}
function getAudio(key) {
  if (cache[key]) return Promise.resolve(cache[key]);
  return api("/v1/review/audio?key=" + encodeURIComponent(key)).then(function (r) {
    if (!r.ok) throw new Error("audio");
    return r.arrayBuffer();
  }).then(function (ab) {
    var url = URL.createObjectURL(new Blob([ab], {type: "audio/wav"}));
    actx = actx || new (window.AudioContext || window.webkitAudioContext)({sampleRate: 48000});
    return actx.decodeAudioData(ab.slice(0)).then(function (buf) { cache[key] = {url: url, buf: buf}; return cache[key]; });
  });
}

function clearCanvas() { [$("spec"), $("wave")].forEach(function (c) { c.getContext("2d").clearRect(0, 0, c.width, c.height); }); }
function fft(re, im) {
  var n = re.length, i, j = 0, k, len, t;
  for (i = 1; i < n; i++) { var bit = n >> 1; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit;
    if (i < j) { t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; } }
  for (len = 2; len <= n; len <<= 1) {
    var ang = -2 * Math.PI / len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (i = 0; i < n; i += len) { var cr = 1, ci = 0;
      for (k = 0; k < len / 2; k++) {
        var a = i + k, b = a + len / 2, xr = re[b] * cr - im[b] * ci, xi = re[b] * ci + im[b] * cr;
        re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
        t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t; } } }
}
function color(v) {   // 0..1 -> dark blue / purple / orange / yellow
  var s = [[0,0,4],[40,11,84],[101,21,110],[159,42,99],[212,72,66],[245,125,21],[250,193,39],[252,255,164]];
  var x = Math.max(0, Math.min(1, v)) * (s.length - 1), i = Math.floor(x), f = x - i, a = s[i], b = s[Math.min(i + 1, s.length - 1)];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
function drawSpec(buf) {
  var x = buf.getChannelData(0), sr = buf.sampleRate, N = 1024, cv = $("spec"), W = cv.width, H = cv.height;
  var hop = Math.max(1, Math.floor((x.length - N) / W)), maxBin = Math.min(N / 2, Math.round(16000 / sr * N));
  var win = new Float32Array(N); for (var i = 0; i < N; i++) win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / N);
  var cols = [], lo = 1e9, hi = -1e9;
  for (var c = 0; c < W; c++) {
    var re = new Float64Array(N), im = new Float64Array(N), o = c * hop;
    for (i = 0; i < N; i++) re[i] = (x[o + i] || 0) * win[i];
    fft(re, im);
    var col = new Float32Array(maxBin);
    for (i = 0; i < maxBin; i++) { col[i] = 10 * Math.log10(re[i] * re[i] + im[i] * im[i] + 1e-12); if (col[i] > hi) hi = col[i]; if (col[i] < lo) lo = col[i]; }
    cols.push(col);
  }
  lo = Math.max(lo, hi - 90);
  var ctx = cv.getContext("2d"), img = ctx.createImageData(W, H);
  for (c = 0; c < W; c++) for (var y = 0; y < H; y++) {
    var bin = Math.floor((H - 1 - y) / H * maxBin), rgb = color((cols[c][bin] - lo) / (hi - lo)), p = (y * W + c) * 4;
    img.data[p] = rgb[0]; img.data[p + 1] = rgb[1]; img.data[p + 2] = rgb[2]; img.data[p + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  ctx.fillStyle = "rgba(255,255,255,.75)"; ctx.font = "11px system-ui";
  [2, 4, 8, 12].forEach(function (k) { var yy = H - k * 1000 / 16000 * H; ctx.fillText(k + " kHz", 4, yy + 4); });
  var wc = $("wave"), wctx = wc.getContext("2d"), ww = wc.width, wh = wc.height, step = Math.ceil(x.length / ww);
  wctx.clearRect(0, 0, ww, wh); wctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--acc");
  for (c = 0; c < ww; c++) { var mn = 1, mx = -1;
    for (i = c * step; i < Math.min(x.length, (c + 1) * step); i++) { if (x[i] < mn) mn = x[i]; if (x[i] > mx) mx = x[i]; }
    wctx.fillRect(c, (1 - mx) * wh / 2, 1, Math.max(1, (mx - mn) * wh / 2)); }
}

function decide(keys, decision) {
  if (!keys.length) return;
  msg("Menyimpan…");
  api("/v1/review/decide", {method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({keys: keys.slice(0, 100), decision: decision})})
    .then(function (r) { return r.json(); }).then(function (j) {
      var gone = Object.keys(j.moved || {});
      var curKey = items[cur] && items[cur].key, idx = cur;
      items = items.filter(function (it) { return gone.indexOf(it.key) < 0; });
      gone.forEach(function (k) { delete picked[k]; });
      msg(gone.length + " sampel " + ({accept: "diterima", reject: "ditolak", review: "dikembalikan"})[decision] +
          (j.ok ? "" : ", sebagian gagal"));
      render(); refreshCounts();
      if (!items.length) { showEmpty(); if (cursor) load(true); return; }
      if (gone.indexOf(curKey) >= 0) select(Math.min(idx, items.length - 1));
      else select(items.findIndex(function (it) { return it.key === curKey; }));
    }).catch(function () {});
}
function decideCur(d) { if (items[cur]) decide([items[cur].key], d); }
$("acc").onclick = function () { decideCur("accept"); };
$("rej").onclick = function () { decideCur("reject"); };
$("back").onclick = function () { decideCur("review"); };
$("play").onclick = function () { if (audio.paused) { audio.currentTime = audio.ended ? 0 : audio.currentTime; audio.play(); } else audio.pause(); };
audio.onplay = function () { $("play").firstChild.textContent = "⏸ Jeda"; };
audio.onpause = function () { $("play").firstChild.textContent = "▶ Putar"; };
document.addEventListener("keydown", function (e) {
  if ($("app").hidden || e.target.tagName === "INPUT" || e.ctrlKey || e.metaKey || e.altKey) return;
  var k = e.key.toLowerCase();
  if (k === " ") { e.preventDefault(); $("play").click(); }
  else if (k === "a" && state !== "accepted") decideCur("accept");
  else if (k === "r" && state !== "rejected") decideCur("reject");
  else if (k === "u" && state !== "review") decideCur("review");
  else if (k === "arrowdown" || k === "j") { e.preventDefault(); select(cur + 1); }
  else if (k === "arrowup" || k === "k") { e.preventDefault(); select(cur - 1); }
});
if (pw) start(); else showLogin();
</script>
</body>
</html>
`;
