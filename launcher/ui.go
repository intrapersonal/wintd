package main

var page = []byte(`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>wintd universal</title>
<style>
:root{--bg:#141517;--panel:#1f2023;--head:#28292d;--field:#2d2e33;--field2:#383940;--seam:#0b0c0d;--fg:#d9d8d3;--fg2:#9d9c97;--fg3:#66666a;--sel:#33527a;--sel2:#4470a4;--ok:#62c26c;--bad:#e2574d;--acc:#e3983f;--ui:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;--mono:"Cascadia Mono",Consolas,ui-monospace,"SF Mono",monospace;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:400 13px/1.45 var(--ui);min-height:100vh;display:flex;justify-content:center;padding:28px 16px}
.win{width:min(640px,100%);background:var(--panel);border:1px solid var(--seam);border-radius:6px;overflow:hidden;box-shadow:0 18px 50px rgba(0,0,0,.5);align-self:flex-start}
.bar{display:flex;align-items:center;gap:9px;height:30px;padding:0 10px;background:var(--head);border-bottom:1px solid var(--seam);font:500 12px var(--mono)}
.mark{width:12px;height:12px;border-radius:2px;background:linear-gradient(#4aa6d8,#4aa6d8) 0 0/6px 6px no-repeat,linear-gradient(#8d71dc,#8d71dc) 6px 0/6px 6px no-repeat,linear-gradient(#49b27c,#49b27c) 0 6px/6px 6px no-repeat,linear-gradient(#d9853b,#d9853b) 6px 6px/6px 6px no-repeat}
.ver{margin-left:auto;color:var(--fg3);font-weight:400}
.body{padding:16px;display:grid;gap:14px}
.det{display:grid;gap:6px}
.lbl{font:500 10.5px var(--mono);color:var(--fg3);text-transform:uppercase;letter-spacing:.08em}
.os{font-size:12px;color:var(--fg2)}
.tool{font:600 22px var(--mono);letter-spacing:-.01em}
.reason{color:var(--fg2);max-width:58ch}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button{font:inherit;color:inherit;height:28px;padding:0 14px;border-radius:3px;border:1px solid var(--seam);background:var(--field);cursor:pointer}
button:hover{background:var(--field2)}
button.primary{background:var(--sel);border-color:#20354f;font-weight:600}
button.primary:hover{background:var(--sel2)}
button:disabled{opacity:.5;cursor:default}
.path{font:400 11.5px var(--mono);color:var(--fg3);overflow-wrap:anywhere}
details{border:1px solid var(--seam);border-radius:4px;background:#232428}
summary{cursor:pointer;padding:7px 10px;font-weight:500;list-style:none;display:flex;gap:8px;align-items:center}
summary::before{content:"";border-left:5px solid var(--fg2);border-top:4px solid transparent;border-bottom:4px solid transparent;transition:transform .12s}
details[open] summary::before{transform:rotate(90deg)}
.adv{padding:4px 10px 12px;display:grid;gap:8px}
.f{display:grid;grid-template-columns:130px minmax(0,1fr);gap:10px;align-items:center}
.f>span{color:var(--fg2);text-align:right}
input[type=text],select{width:100%;height:24px;background:#17181b;border:1px solid var(--seam);border-radius:3px;color:var(--fg);font:400 12px var(--mono);padding:0 8px}
input[type=text]:focus,select:focus{outline:1px solid var(--sel2)}
.checks{display:flex;gap:12px;flex-wrap:wrap}
.checks label{display:flex;gap:5px;align-items:center;color:var(--fg)}
.note{font-size:11.5px;color:var(--fg3)}
.log{background:#111214;border:1px solid var(--seam);border-radius:3px;font:400 11.5px/1.55 var(--mono);height:190px;overflow:auto;padding:6px 9px;white-space:pre-wrap;color:var(--fg2)}
.log .s{color:#7fa6d6}
.log .e{color:var(--bad)}
.status{display:flex;gap:8px;align-items:center;font:500 11.5px var(--mono);color:var(--fg2)}
.dot{width:8px;height:8px;border-radius:50%;background:#3a3b40}
.dot.run{background:var(--acc);box-shadow:0 0 6px rgba(227,152,63,.7)}
.dot.ok{background:var(--ok)}
.dot.bad{background:var(--bad)}
.warn{border-left:2px solid var(--acc);padding:6px 10px;background:#2a2620;color:#e9d3b4;font-size:12px}
@media (max-width:520px){.f{grid-template-columns:1fr}.f>span{text-align:left}}
</style>
</head>
<body>
<div class="win">
  <div class="bar"><span class="mark"></span>wintd universal<span class="ver" id="ver"></span></div>
  <div class="body">
    <div class="det">
      <span class="lbl">this computer</span>
      <span class="os" id="os">checking…</span>
      <span class="tool" id="tool">…</span>
      <span class="reason" id="reason"></span>
    </div>
    <div class="warn" id="warn" hidden></div>
    <div class="row">
      <button class="primary" id="go" disabled>Install</button>
      <span class="path" id="dest"></span>
    </div>
    <details id="advanced">
      <summary>Advanced</summary>
      <div class="adv">
        <label class="f"><span>Install</span><select id="pick">
          <option value="auto">Auto (recommended)</option>
          <option value="wintd">wintd (Windows)</option>
          <option value="appletd">appletd (Apple Silicon)</option>
          <option value="sidecar">wintd network sender (Linux)</option>
        </select></label>
        <label class="f"><span>Component folder</span><input type="text" id="folder" spellcheck="false"></label>
        <label class="f"><span>Python + models</span><input type="text" id="root" spellcheck="false"></label>
        <label class="f" id="pyrow"><span>Base python</span><select id="python"></select></label>
        <label class="f" id="hostrow"><span>Send to (TD machine)</span><input type="text" id="host" placeholder="192.168.1.20" spellcheck="false"></label>
        <div class="f"><span>Prefetch models</span><div class="checks">
          <label><input type="checkbox" value="hands" checked disabled>hands</label>
          <label><input type="checkbox" value="face">face</label>
          <label><input type="checkbox" value="pose">pose</label>
          <label><input type="checkbox" value="segment">body mask</label>
          <label><input type="checkbox" value="depth">depth</label>
        </div></div>
        <div class="f"><span></span><div class="checks">
          <label><input type="checkbox" id="keep">keep downloads</label>
          <label><input type="checkbox" id="dry">dry run</label>
        </div></div>
        <span class="note">anything you don't prefetch downloads the first time you turn it on.</span>
      </div>
    </details>
    <div class="status"><span class="dot" id="dot"></span><span id="step">idle</span></div>
    <div class="log" id="log"></div>
    <div class="row">
      <button id="open" disabled>Open Folder</button>
      <button id="quit">Close</button>
    </div>
  </div>
</div>
<script>
const T = "__TOKEN__";
const $ = (id) => document.getElementById(id);
let info = null, polling = false, outPath = "";
const api = (p, body) => fetch(p, { method: body ? "POST" : "GET", headers: { "X-Token": T, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
const NAMES = { wintd: "wintd", appletd: "appletd", sidecar: "wintd network sender", "mediapipe-td": "mediapipe plugin" };
function tool() { const v = $("pick").value; return v === "auto" ? info.tool : v; }
function refresh() {
  const t = tool();
  $("tool").textContent = NAMES[t] || t;
  $("go").textContent = "Install " + (NAMES[t] || t);
  $("pyrow").hidden = t !== "sidecar";
  $("hostrow").hidden = t !== "sidecar";
  $("dest").textContent = "→ " + $("folder").value;
  const blocked = $("pick").value === "auto" && !info.supported;
  $("go").disabled = blocked || polling;
  $("warn").hidden = !blocked;
  if (blocked) $("warn").textContent = info.tool === "mediapipe-td" ? "nothing to install from here. grab the mediapipe touchdesigner plugin from github (torinmb/mediapipe-touchdesigner)." : "this machine isn't supported. pick a tool under Advanced if you know what you're doing.";
}
async function load() {
  info = await (await api("/api/info")).json();
  $("ver").textContent = info.version;
  $("os").textContent = info.pretty;
  $("reason").textContent = info.reason;
  $("folder").value = info.folder;
  $("root").value = info.root;
  $("python").innerHTML = "";
  (info.pythons.length ? info.pythons : [""]).forEach((p) => { const o = document.createElement("option"); o.value = p; o.textContent = p || "none found"; $("python").append(o); });
  refresh();
}
function render(s) {
  const log = $("log");
  log.innerHTML = "";
  for (const l of s.lines) {
    const d = document.createElement("div");
    if (l.startsWith("== ")) { d.className = "s"; d.textContent = l.slice(3); }
    else if (l.startsWith("failed")) { d.className = "e"; d.textContent = l; }
    else d.textContent = l;
    log.append(d);
  }
  log.scrollTop = log.scrollHeight;
  $("step").textContent = s.error ? "failed" : s.done ? (s.step === "dry run" ? "dry run finished" : "done") : (s.step || "starting");
  $("dot").className = "dot " + (s.error ? "bad" : s.done ? "ok" : "run");
  if (s.output) { outPath = s.output; $("open").disabled = false; }
}
async function poll() {
  const s = await (await api("/api/progress")).json();
  render(s);
  if (s.active || !s.done) { setTimeout(poll, 700); return; }
  polling = false;
  refresh();
}
$("pick").addEventListener("change", refresh);
$("folder").addEventListener("input", refresh);
$("go").addEventListener("click", async () => {
  const streams = ["hands", ...[...document.querySelectorAll(".checks input[value]")].filter((c) => c.checked && c.value !== "hands").map((c) => c.value)];
  const body = { tool: tool(), folder: $("folder").value.trim(), root: $("root").value.trim(), python: $("python").value, host: $("host").value.trim(), streams, keep: $("keep").checked, dryRun: $("dry").checked };
  const r = await api("/api/install", body);
  if (!r.ok) { $("step").textContent = await r.text(); return; }
  polling = true;
  refresh();
  poll();
});
$("open").addEventListener("click", () => api("/api/open?path=" + encodeURIComponent(outPath)));
$("quit").addEventListener("click", async () => { await api("/api/quit"); document.body.innerHTML = "<p style='color:#9d9c97;font:13px system-ui;padding:40px'>closed. you can close this tab.</p>"; });
setInterval(() => api("/api/progress"), 30000);
load();
</script>
</body>
</html>
`)
