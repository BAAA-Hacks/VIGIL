#pragma once

#include <Arduino.h>

// Debug/viewer page served at "/". The ground station consumes /raw through a laptop adapter;
// this page is for checking the camera directly from a browser.
static const char WEB_PAGE[] PROGMEM = R"HTML(<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lepton Camera</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; padding: 16px; background: #111; color: #ddd; font: 14px system-ui, sans-serif; }
  main { max-width: 680px; margin: 0 auto; }
  h1 { font-size: 18px; margin: 0 0 12px; }
  #view { width: 100%; background: #000; display: block; min-height: 120px; image-rendering: auto; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; margin: 12px 0; }
  .stats { font-family: ui-monospace, monospace; font-size: 13px; color: #aaa; }
  .ok { color: #7c7; } .bad { color: #e77; }
  button, select { background: #222; color: #ddd; border: 1px solid #444; border-radius: 4px; padding: 4px 10px; font: inherit; }
  button.active { border-color: #7cf; color: #7cf; }
</style>
</head>
<body>
<main>
  <h1>Lepton 3.5 thermal camera</h1>
  <img id="view" src="/stream" alt="Thermal stream">
  <div class="bar stats">
    <span>State: <b id="state">-</b></span>
    <span>FPS: <b id="fps">-</b></span>
    <span>Frames: <b id="frames">-</b></span>
    <span>Invalid: <b id="invalid">-</b></span>
    <span>Resyncs: <b id="resyncs">-</b></span>
    <span>Heap: <b id="heap">-</b></span>
  </div>
  <div class="bar">
    <label>Palette
      <select id="palette">
        <option value="gray">Grayscale</option>
        <option value="iron">Iron</option>
        <option value="rainbow">Rainbow</option>
      </select>
    </label>
    <span>Rotate
      <button data-rot="0">0&deg;</button><button data-rot="90">90&deg;</button><button data-rot="180">180&deg;</button><button data-rot="270">270&deg;</button>
    </span>
    <label><input type="checkbox" id="mirror"> Mirror</label>
    <a href="/capture" target="_blank" style="color:#7cf">Snapshot</a>
  </div>
</main>
<script>
const $ = (id) => document.getElementById(id);
const view = $('view');

// Reconnect the MJPEG stream if it drops (camera reset, Wi-Fi hiccup).
view.onerror = () => setTimeout(() => { view.src = '/stream?t=' + Date.now(); }, 1000);

function showSettings(s) {
  $('palette').value = s.palette;
  $('mirror').checked = s.mirror;
  document.querySelectorAll('[data-rot]').forEach((b) => b.classList.toggle('active', +b.dataset.rot === s.rotation));
}

function applySettings(params) {
  fetch('/settings?' + new URLSearchParams(params)).then((r) => r.json()).then(showSettings).catch(() => {});
}

$('palette').onchange = (e) => applySettings({ palette: e.target.value });
$('mirror').onchange = (e) => applySettings({ mirror: e.target.checked ? 1 : 0 });
document.querySelectorAll('[data-rot]').forEach((b) => { b.onclick = () => applySettings({ rotation: b.dataset.rot }); });

async function poll() {
  try {
    const s = await (await fetch('/status')).json();
    $('state').textContent = s.cameraState;
    $('state').className = s.cameraState === 'streaming' && s.fps > 0 ? 'ok' : 'bad';
    $('fps').textContent = s.fps.toFixed(1);
    $('frames').textContent = s.framesCaptured;
    $('invalid').textContent = s.framesInvalid;
    $('resyncs').textContent = s.resyncs;
    $('heap').textContent = Math.round(s.freeHeap / 1024) + ' KB';
  } catch (e) {
    $('state').textContent = 'offline';
    $('state').className = 'bad';
  }
}

fetch('/settings').then((r) => r.json()).then(showSettings).catch(() => {});
poll();
setInterval(poll, 1000);
</script>
</body>
</html>
)HTML";
