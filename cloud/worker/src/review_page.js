// The developer review page served at /review. Plain HTML + JS, no dependencies.
// (Kept as a string so the Worker stays a single bundle; the page uses no backticks or "${".)
export const REVIEW_PAGE = String.raw`<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Review sampel noise · Noise Filter</title>
<link rel="icon" href="/review/logo.png">
<style>
:root {
  --bg:#f5f7fa; --panel:#ffffff; --ink:#0f172a; --ink2:#475569; --mute:#94a3b8; --line:#e5e9f0; --hover:#f1f5f9;
  --acc:#0ea5e9; --acc-ink:#ffffff; --accsoft:#e0f2fe; --ok:#16a34a; --oksoft:#dcfce7; --bad:#dc2626; --badsoft:#fee2e2;
  --shadow:0 1px 2px rgba(15,23,42,.04), 0 4px 16px rgba(15,23,42,.05); --r:12px;
}
@media (prefers-color-scheme: dark) { :root {
  --bg:#0b1120; --panel:#111a2e; --ink:#e2e8f0; --ink2:#94a3b8; --mute:#64748b; --line:#1e293b; --hover:#16213a;
  --acc:#38bdf8; --acc-ink:#04121f; --accsoft:#0c2a40; --ok:#22c55e; --oksoft:#0f2e1c; --bad:#f87171; --badsoft:#3a1515;
  --shadow:0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.25); } }
* { box-sizing:border-box }
html, body { height:100% }
body { margin:0; font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--ink); -webkit-font-smoothing:antialiased }
[hidden] { display:none !important }
button { font:inherit; color:inherit }
svg { width:18px; height:18px; flex:none; stroke:currentColor; fill:none; stroke-width:2; stroke-linecap:round; stroke-linejoin:round }
.btn { display:inline-flex; align-items:center; justify-content:center; gap:8px; height:38px; padding:0 16px; border-radius:10px;
       border:1px solid var(--line); background:var(--panel); cursor:pointer; font-weight:500; transition:background .15s, opacity .15s }
.btn:hover:not(:disabled) { background:var(--hover) }
.btn:disabled { opacity:.4; cursor:default }
.btn.ok { background:var(--ok); border-color:var(--ok); color:#fff } .btn.ok:hover:not(:disabled) { background:var(--ok); opacity:.9 }
.btn.bad { background:transparent; border-color:var(--bad); color:var(--bad) } .btn.bad:hover:not(:disabled) { background:var(--badsoft) }
.btn.ghost { border-color:transparent; background:transparent; color:var(--ink2) }
.btn.sm { height:32px; padding:0 12px; font-size:13px }
.icon-btn { width:38px; padding:0 }
kbd { font:600 10px ui-monospace,monospace; padding:1px 5px; border-radius:4px; background:rgba(127,127,127,.18); opacity:.85 }

/* login */
#login { min-height:100%; display:grid; place-items:center; padding:24px;
         background:radial-gradient(1200px 600px at 50% -10%, var(--accsoft), transparent 70%) }
.login-card { width:100%; max-width:360px; background:var(--panel); border:1px solid var(--line); border-radius:16px; box-shadow:var(--shadow); padding:32px }
.login-card img { width:56px; height:56px; border-radius:14px; display:block; margin:0 auto 16px }
.login-card h1 { font-size:18px; text-align:center; margin:0 }
.login-card p { text-align:center; color:var(--ink2); margin:4px 0 24px; font-size:13px }
.field { position:relative }
.field input { width:100%; height:42px; padding:0 42px 0 14px; border:1px solid var(--line); border-radius:10px; background:var(--bg); color:var(--ink); font:inherit; outline:none }
.field input:focus { border-color:var(--acc); box-shadow:0 0 0 3px var(--accsoft) }
.field button { position:absolute; right:4px; top:4px; height:34px; width:34px; border:0; background:none; color:var(--mute); cursor:pointer; display:grid; place-items:center }
.check { display:flex; align-items:center; gap:8px; margin:14px 0 20px; color:var(--ink2); font-size:13px; cursor:pointer }
.check input { accent-color:var(--acc); width:15px; height:15px; margin:0 }
.primary { width:100%; height:42px; border:0; border-radius:10px; background:var(--acc); color:var(--acc-ink); font-weight:600; cursor:pointer }
.primary:hover { filter:brightness(1.05) }
.err { color:var(--bad); font-size:13px; text-align:center; margin-top:12px } .err:empty { display:none }

/* app */
#app { min-height:100% }
.top { height:60px; display:flex; align-items:center; gap:12px; padding:0 24px; background:var(--panel); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:5 }
.top img { width:30px; height:30px; border-radius:8px }
.brand b { display:block; font-size:14px; line-height:1.2 } .brand span { font-size:12px; color:var(--mute) }
.top .grow { flex:1 }
.wrap { max-width:1360px; margin:0 auto; padding:20px 24px 32px }
.stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:20px }
.stat { text-align:left; background:var(--panel); border:1px solid var(--line); border-radius:var(--r); padding:14px 16px; cursor:pointer; transition:border-color .15s, box-shadow .15s }
.stat:hover { border-color:var(--mute) }
.stat.on { border-color:var(--acc); box-shadow:0 0 0 3px var(--accsoft) }
.stat span { display:block; font-size:12px; color:var(--ink2); font-weight:500 }
.stat b { display:block; font-size:24px; font-weight:650; margin-top:2px; font-variant-numeric:tabular-nums }
.grid { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.15fr); gap:20px; align-items:start }
.card { background:var(--panel); border:1px solid var(--line); border-radius:var(--r); box-shadow:var(--shadow) }
.bar { display:flex; align-items:center; gap:8px; padding:10px 12px; border-bottom:1px solid var(--line); min-height:54px }
.bar .count { color:var(--mute); font-size:13px; margin-right:auto; padding-left:4px }
.list { max-height:calc(100vh - 260px); overflow:auto }
.row { display:grid; grid-template-columns:28px minmax(0,1fr) auto; gap:10px; align-items:center; padding:10px 12px; border-bottom:1px solid var(--line); cursor:pointer }
.row:last-child { border-bottom:0 }
.row:hover { background:var(--hover) }
.row.cur { background:var(--accsoft) }
.row input, .bar input { accent-color:var(--acc); width:15px; height:15px; margin:0 auto; display:block }
.bar input { margin:0 6px 0 4px; flex:none }
.row .t { font-weight:550; white-space:nowrap; overflow:hidden; text-overflow:ellipsis }
.row .s { font-size:12px; color:var(--mute); display:flex; gap:6px; align-items:center }
.row .s svg { width:13px; height:13px }
.pill { font-size:11px; font-weight:600; padding:2px 8px; border-radius:999px; background:var(--hover); color:var(--ink2); white-space:nowrap }
.pill.ok { background:var(--oksoft); color:var(--ok) } .pill.bad { background:var(--badsoft); color:var(--bad) }
.more { padding:12px; text-align:center }
.empty { padding:64px 24px; text-align:center; color:var(--mute) }
.empty svg { width:36px; height:36px; stroke-width:1.5; margin-bottom:8px }

.player { padding:16px; position:sticky; top:80px }
.viz { position:relative; border-radius:10px; overflow:hidden; background:#000; cursor:pointer }
#spec { width:100%; height:240px; display:block }
#head { position:absolute; top:0; bottom:0; width:2px; background:#fff; opacity:.85; left:0; pointer-events:none; display:none }
.axis { position:absolute; left:8px; font:10px ui-monospace,monospace; color:rgba(255,255,255,.7); pointer-events:none }
.controls { display:flex; align-items:center; gap:10px; margin-top:14px; flex-wrap:wrap }
.play { width:44px; height:44px; border-radius:50%; border:0; background:var(--acc); color:var(--acc-ink); display:grid; place-items:center; cursor:pointer; flex:none }
.play svg { width:20px; height:20px; fill:currentColor; stroke:none }
.time { font:12px ui-monospace,monospace; color:var(--ink2); min-width:84px }
.controls .grow { flex:1 } .brk { display:none }
.title { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:18px 0 10px }
.title b { font-size:16px }
dl { display:grid; grid-template-columns:auto 1fr; gap:6px 16px; margin:0; font-size:13px }
dt { color:var(--mute) } dd { margin:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.toast { position:fixed; left:50%; bottom:24px; transform:translate(-50%, 20px); opacity:0; pointer-events:none; transition:all .2s;
         background:var(--ink); color:var(--bg); border-radius:10px; padding:10px 10px 10px 16px; display:flex; align-items:center; gap:12px; box-shadow:var(--shadow); z-index:10; white-space:nowrap }
.toast.show { opacity:1; transform:translate(-50%, 0); pointer-events:auto }
.toast button { border:0; background:transparent; color:var(--acc); font-weight:600; cursor:pointer; padding:4px 8px }
@media (max-width:960px) {
  .grid { grid-template-columns:1fr } .player { position:static; order:-1 } .list { max-height:none }
  .stats { grid-template-columns:repeat(2,minmax(0,1fr)) }
}
@media (max-width:560px) {
  .top, .wrap { padding-left:16px; padding-right:16px } #spec { height:180px }
  .stats { grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin-bottom:16px }
  .stat { padding:10px; text-align:center } .stat span { font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis } .stat b { font-size:18px }
  .time { flex:1 } .controls .grow { display:none } .controls .btn { flex:1 } .brk { display:block; flex-basis:100%; height:0 } kbd { display:none }
}
</style>
</head>
<body>
<svg style="display:none" xmlns="http://www.w3.org/2000/svg">
  <symbol id="i-mic" viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></symbol>
  <symbol id="i-file" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></symbol>
  <symbol id="i-x" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></symbol>
  <symbol id="i-undo" viewBox="0 0 24 24"><path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/></symbol>
  <symbol id="i-out" viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/></symbol>
  <symbol id="i-eye" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></symbol>
  <symbol id="i-inbox" viewBox="0 0 24 24"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/></symbol>
  <symbol id="i-play" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></symbol>
  <symbol id="i-pause" viewBox="0 0 24 24"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></symbol>
</svg>

<div id="login" hidden>
  <form class="login-card" id="loginf">
    <img src="/review/logo.png" alt="">
    <h1>Noise Filter</h1>
    <p>Review sampel noise</p>
    <div class="field">
      <input id="pw" type="password" autocomplete="current-password" placeholder="Password" required>
      <button type="button" id="peek" aria-label="Tampilkan password"><svg><use href="#i-eye"/></svg></button>
    </div>
    <label class="check"><input id="remember" type="checkbox"> Ingat saya</label>
    <button class="primary" type="submit">Masuk</button>
    <div class="err" id="loginerr"></div>
  </form>
</div>

<div id="app" hidden>
  <header class="top">
    <img src="/review/logo.png" alt="">
    <div class="brand"><b>Noise Filter</b><span>Review sampel</span></div>
    <div class="grow"></div>
    <button class="btn ghost icon-btn" id="logout" title="Keluar" aria-label="Keluar"><svg><use href="#i-out"/></svg></button>
  </header>
  <div class="wrap">
    <nav class="stats" id="tabs"></nav>
    <div class="grid">
      <section class="card">
        <div class="bar">
          <input type="checkbox" id="all" title="Pilih semua" aria-label="Pilih semua">
          <span class="count" id="npick"></span>
          <button class="btn sm ok" id="bacc" hidden><svg><use href="#i-check"/></svg>Terima</button>
          <button class="btn sm bad" id="brej" hidden><svg><use href="#i-x"/></svg>Tolak</button>
        </div>
        <div class="list" id="list"></div>
      </section>
      <section class="card player">
        <div id="pempty" class="empty"><svg><use href="#i-inbox"/></svg><div>Tidak ada sampel</div></div>
        <div id="pbody" hidden>
          <div class="viz" id="viz">
            <canvas id="spec" width="1200" height="240"></canvas>
            <div id="head"></div>
            <span class="axis" style="top:6px">16 kHz</span><span class="axis" style="top:calc(50% - 6px)">8 kHz</span><span class="axis" style="bottom:6px">0</span>
          </div>
          <div class="controls">
            <button class="play" id="play" title="Putar (Spasi)" aria-label="Putar"><svg><use href="#i-play"/></svg></button>
            <span class="time" id="time">0:00 / 0:00</span>
            <span class="grow"></span><span class="brk"></span>
            <button class="btn" id="back" title="Kembalikan ke antrean (U)"><svg><use href="#i-undo"/></svg>Antrean</button>
            <button class="btn bad" id="rej" title="Tolak (R)"><svg><use href="#i-x"/></svg>Tolak<kbd>R</kbd></button>
            <button class="btn ok" id="acc" title="Terima (A)"><svg><use href="#i-check"/></svg>Terima<kbd>A</kbd></button>
          </div>
          <div class="title"><b id="ptitle"></b><span id="pstatus"></span></div>
          <dl id="meta"></dl>
        </div>
      </section>
    </div>
  </div>
</div>
<div class="toast" id="toast"><span id="toastmsg"></span><button id="undo">Batalkan</button></div>

<script>
"use strict";
var STATES = [["review","Antrean"],["accepted","Diterima"],["rejected","Ditolak"],["incoming","Baru"]];
var BACK = {review:"review", accepted:"accept", rejected:"reject"};
var CAT = {fan_ac:"Kipas / AC", traffic:"Lalu lintas", keyboard:"Keyboard", crowd:"Keramaian",
           machine:"Mesin", rain_wind:"Hujan / angin", other:"Lainnya"};
var REASON = {ok:"Lolos", speech:"Ada suara", silent:"Sunyi", clipped:"Clipping", duplicate:"Duplikat",
              "daily cap":"Batas harian", "too short":"Terlalu pendek", "too long":"Terlalu panjang"};
var pw = "";
try { pw = sessionStorage.getItem("nfpw") || localStorage.getItem("nfpw") || ""; } catch (e) {}
var state = "review", items = [], cursor = null, cur = -1, picked = {}, counts = {};
var audio = new Audio(), actx = null, cache = {}, toastTimer = 0, lastUndo = null;
var $ = function (id) { return document.getElementById(id); };
function store(k, v) { try { if (v == null) { sessionStorage.removeItem(k); localStorage.removeItem(k); } else sessionStorage.setItem(k, v); } catch (e) {} }

function api(path, opts) {
  opts = opts || {};
  opts.headers = Object.assign({authorization: "Bearer " + pw}, opts.headers || {});
  return fetch(path, opts).then(function (r) {
    if (r.status === 401 || r.status === 429) { showLogin(r.status === 429 ? "Terlalu banyak percobaan. Coba lagi 1 menit lagi." : "Password salah."); throw new Error("auth"); }
    return r;
  });
}
function showLogin(err) { $("app").hidden = true; $("login").hidden = false; $("loginerr").textContent = err || ""; $("pw").value = ""; $("pw").focus(); }
$("peek").onclick = function () { $("pw").type = $("pw").type === "password" ? "text" : "password"; };
$("loginf").onsubmit = function (e) {
  e.preventDefault(); pw = $("pw").value; store("nfpw", pw);
  if ($("remember").checked) { try { localStorage.setItem("nfpw", pw); } catch (x) {} }
  start();
};
$("logout").onclick = function () { store("nfpw", null); pw = ""; audio.pause(); showLogin(); };

function start() {
  api("/v1/review/stats").then(function (r) { return r.json(); }).then(function (j) {
    if (!j.ok) { showLogin(j.error); return; }
    $("login").hidden = true; $("app").hidden = false; counts = j.counts; tabs(); load(true);
  }).catch(function () {});
}
function tabs() {
  $("tabs").innerHTML = STATES.map(function (s) {
    return '<button class="stat' + (s[0] === state ? " on" : "") + '" data-s="' + s[0] + '"><span>' + s[1] + "</span><b>" + (counts[s[0]] || 0) + "</b></button>";
  }).join("");
  Array.prototype.forEach.call($("tabs").children, function (b) { b.onclick = function () { state = b.dataset.s; tabs(); load(true); }; });
}
function refreshCounts() { api("/v1/review/stats").then(function (r) { return r.json(); }).then(function (j) { if (j.ok) { counts = j.counts; tabs(); } }).catch(function () {}); }

function load(reset) {
  if (reset) { items = []; cursor = null; cur = -1; picked = {}; }
  api("/v1/review/list?state=" + state + (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""))
    .then(function (r) { return r.json(); }).then(function (j) {
      items = items.concat(j.items); cursor = j.cursor; render();
      if (reset) { if (items.length) select(0); else showEmpty(); }
    }).catch(function () {});
}

function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return "&#" + c.charCodeAt(0) + ";"; }); }
function day(k) { var d = new Date(k.split("/")[2].slice(0, 10) + "T00:00:00Z");
  return isNaN(d) ? "" : d.toLocaleDateString("id-ID", {day: "numeric", month: "short", year: "numeric", timeZone: "UTC"}); }
function secs(m) { return m.seconds ? (+m.seconds).toFixed(1) + " dtk" : ""; }
function pill(m) {
  if (m.reviewed) return m.reviewed.indexOf("accept") === 0 ? '<span class="pill ok">Diterima</span>' : '<span class="pill bad">Ditolak</span>';
  if (!m.reason) return '<span class="pill">Belum dicek</span>';
  var r = m.reason.indexOf("manual") === 0 ? "Ditolak" : (REASON[m.reason] || (m.reason.indexOf("bad wav") === 0 ? "File rusak" : m.reason));
  return '<span class="pill ' + (m.reason === "ok" ? "ok" : "bad") + '">' + esc(r) + "</span>";
}

function render() {
  if (!items.length) {
    $("list").innerHTML = '<div class="empty"><svg><use href="#i-inbox"/></svg><div>Kosong</div></div>';
  } else {
    $("list").innerHTML = items.map(function (it, i) {
      var m = it.meta || {};
      return '<div class="row' + (i === cur ? " cur" : "") + '" data-i="' + i + '">' +
        '<input type="checkbox" data-k="' + i + '"' + (picked[it.key] ? " checked" : "") + ' aria-label="Pilih">' +
        '<div><div class="t">' + esc(CAT[m.category] || m.category || "Tanpa jenis") + '</div>' +
        '<div class="s"><svg><use href="#i-' + (m.source === "file" ? "file" : "mic") + '"/></svg>' + esc(secs(m)) + " · " + esc(day(it.key)) + "</div></div>" +
        pill(m) + "</div>";
    }).join("") + (cursor ? '<div class="more"><button class="btn sm" id="more">Muat lagi</button></div>' : "");
  }
  Array.prototype.forEach.call(document.querySelectorAll(".row"), function (r) {
    r.onclick = function (e) { if (e.target.type !== "checkbox") select(+r.dataset.i); };
  });
  Array.prototype.forEach.call(document.querySelectorAll("input[data-k]"), function (cb) {
    cb.onchange = function () { var k = items[+cb.dataset.k].key; if (cb.checked) picked[k] = 1; else delete picked[k]; pickInfo(); };
  });
  if ($("more")) $("more").onclick = function () { load(false); };
  pickInfo();
}
$("all").onchange = function () { picked = {}; if ($("all").checked) items.forEach(function (it) { picked[it.key] = 1; }); render(); };
$("bacc").onclick = function () { decide(Object.keys(picked), "accept"); };
$("brej").onclick = function () { decide(Object.keys(picked), "reject"); };
function pickInfo() {
  var n = Object.keys(picked).length;
  $("npick").textContent = n ? n + " dipilih" : items.length + " sampel";
  $("bacc").hidden = !n || state === "accepted"; $("brej").hidden = !n || state === "rejected";
  $("all").checked = n > 0 && n === items.length; $("all").disabled = !items.length;
}

function showEmpty() { $("pbody").hidden = true; $("pempty").hidden = false; audio.pause(); }
function fmt(t) { t = Math.max(0, t || 0); return Math.floor(t / 60) + ":" + ("0" + Math.floor(t % 60)).slice(-2); }
function select(i) {
  if (i < 0 || i >= items.length) return;
  cur = i; var it = items[i], m = it.meta || {};
  Array.prototype.forEach.call(document.querySelectorAll(".row"), function (r) { r.classList.toggle("cur", +r.dataset.i === i); });
  var row = document.querySelector('.row[data-i="' + i + '"]'); if (row) row.scrollIntoView({block: "nearest"});
  $("pempty").hidden = true; $("pbody").hidden = false;
  $("acc").hidden = state === "accepted"; $("rej").hidden = state === "rejected"; $("back").hidden = state === "review" || state === "incoming";
  $("ptitle").textContent = CAT[m.category] || m.category || "Tanpa jenis";
  $("pstatus").innerHTML = pill(m);
  var rows = [["Sumber", m.source === "file" ? "File pengguna" : "Mikrofon"], ["Durasi", secs(m)], ["Tanggal", day(it.key)],
              ["Aplikasi", m.app_version ? "v" + m.app_version + " · " + (m.os || "") : ""], ["Instalasi", it.key.split("/")[1].slice(0, 8)]];
  $("meta").innerHTML = rows.filter(function (r) { return r[1]; }).map(function (r) { return "<dt>" + esc(r[0]) + "</dt><dd>" + esc(r[1]) + "</dd>"; }).join("");
  audio.pause(); $("head").style.display = "none"; $("time").textContent = "0:00 / " + fmt(m.seconds);
  var c = $("spec"); c.getContext("2d").clearRect(0, 0, c.width, c.height);
  getAudio(it.key).then(function (d) {
    if (items[cur] !== it) return;
    audio.src = d.url; drawSpec(d.buf);
    audio.play().catch(function () {});
  }).catch(function (e) { if (e.message !== "auth") toast("Audio gagal dimuat"); });
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
function color(v) {   // black -> deep blue -> cyan -> white, matching the app logo
  var s = [[0,0,0],[6,18,48],[10,55,120],[14,120,200],[56,189,248],[165,232,255],[255,255,255]];
  var x = Math.max(0, Math.min(1, v)) * (s.length - 1), i = Math.floor(x), f = x - i, a = s[i], b = s[Math.min(i + 1, s.length - 1)];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
function drawSpec(buf) {
  var x = buf.getChannelData(0), sr = buf.sampleRate, N = 1024, cv = $("spec"), W = cv.width, H = cv.height;
  var hop = Math.max(1, Math.floor((x.length - N) / W)), maxBin = Math.min(N / 2, Math.round(16000 / sr * N));
  var win = new Float32Array(N), i, c;
  for (i = 0; i < N; i++) win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / N);
  var cols = [], hi = -1e9;
  for (c = 0; c < W; c++) {
    var re = new Float64Array(N), im = new Float64Array(N), o = c * hop;
    for (i = 0; i < N; i++) re[i] = (x[o + i] || 0) * win[i];
    fft(re, im);
    var col = new Float32Array(maxBin);
    for (i = 0; i < maxBin; i++) { col[i] = 10 * Math.log10(re[i] * re[i] + im[i] * im[i] + 1e-12); if (col[i] > hi) hi = col[i]; }
    cols.push(col);
  }
  var lo = hi - 80, ctx = cv.getContext("2d"), img = ctx.createImageData(W, H);
  for (c = 0; c < W; c++) for (var y = 0; y < H; y++) {
    var rgb = color((cols[c][Math.floor((H - 1 - y) / H * maxBin)] - lo) / (hi - lo)), p = (y * W + c) * 4;
    img.data[p] = rgb[0]; img.data[p + 1] = rgb[1]; img.data[p + 2] = rgb[2]; img.data[p + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
}
function tick() {
  if (audio.duration) {
    $("head").style.display = "block"; $("head").style.left = (audio.currentTime / audio.duration * 100) + "%";
    $("time").textContent = fmt(audio.currentTime) + " / " + fmt(audio.duration);
  }
  if (!audio.paused) requestAnimationFrame(tick);
}
audio.onplay = function () { $("play").innerHTML = '<svg><use href="#i-pause"/></svg>'; tick(); };
audio.onpause = audio.onended = function () { $("play").innerHTML = '<svg><use href="#i-play"/></svg>'; tick(); };
$("play").onclick = function () { if (audio.paused) audio.play().catch(function () {}); else audio.pause(); };
$("viz").onclick = function (e) {
  if (!audio.duration) return;
  var r = $("viz").getBoundingClientRect(); audio.currentTime = (e.clientX - r.left) / r.width * audio.duration;
  if (audio.paused) audio.play().catch(function () {}); else tick();
};

function toast(text, undo) {
  $("toastmsg").textContent = text; lastUndo = undo || null; $("undo").hidden = !undo;
  $("toast").classList.add("show"); clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { $("toast").classList.remove("show"); lastUndo = null; }, 5000);
}
$("undo").onclick = function () {
  var u = lastUndo; if (!u) return; lastUndo = null; $("toast").classList.remove("show");
  api("/v1/review/decide", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(u)})
    .then(function () { load(true); refreshCounts(); }).catch(function () {});
};
function decide(keys, decision) {
  if (!keys.length) return;
  var from = state;
  api("/v1/review/decide", {method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({keys: keys.slice(0, 100), decision: decision})})
    .then(function (r) { return r.json(); }).then(function (j) {
      var moved = j.moved || {}, gone = Object.keys(moved);
      var curKey = items[cur] && items[cur].key, idx = cur;
      items = items.filter(function (it) { return !(it.key in moved); });
      gone.forEach(function (k) { delete picked[k]; });
      var word = {accept: "diterima", reject: "ditolak", review: "dikembalikan ke antrean"}[decision];
      var dest = gone.map(function (k) { return moved[k]; });
      toast((gone.length === 1 ? "Sampel " : gone.length + " sampel ") + word + (j.ok ? "" : " (sebagian gagal)"),
            BACK[from] && dest.length ? {keys: dest, decision: BACK[from]} : null);
      render(); refreshCounts();
      if (!items.length) { showEmpty(); if (cursor) load(true); return; }
      if (curKey in moved) select(Math.min(idx, items.length - 1));
      else select(items.findIndex(function (it) { return it.key === curKey; }));
    }).catch(function () {});
}
function decideCur(d) { if (items[cur]) decide([items[cur].key], d); }
$("acc").onclick = function () { decideCur("accept"); };
$("rej").onclick = function () { decideCur("reject"); };
$("back").onclick = function () { decideCur("review"); };
document.addEventListener("keydown", function (e) {
  if ($("app").hidden || e.target.tagName === "INPUT" || e.ctrlKey || e.metaKey || e.altKey) return;
  var k = e.key.toLowerCase();
  if (k === " ") { e.preventDefault(); $("play").click(); }
  else if (k === "a" && state !== "accepted") decideCur("accept");
  else if (k === "r" && state !== "rejected") decideCur("reject");
  else if (k === "u" && BACK[state] && state !== "review") decideCur("review");
  else if (k === "z" && lastUndo) $("undo").click();
  else if (k === "arrowdown" || k === "j") { e.preventDefault(); select(cur + 1); }
  else if (k === "arrowup" || k === "k") { e.preventDefault(); select(cur - 1); }
});
if (pw) start(); else showLogin();
</script>
</body>
</html>
`;
