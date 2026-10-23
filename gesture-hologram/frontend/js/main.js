import { BackendSocket } from './socket.js';
import { Scene } from './scene.js';
import { drawHologram } from './hologram.js';
import { Hud } from './hud.js';
import { loadPrefs, savePrefs } from './prefs.js';

const $ = (id) => document.getElementById(id);
const root = document.documentElement;

const canvas = $('stage');
const ctx = canvas.getContext('2d', { alpha: false });
const SCENE_PX = 1024;
const sceneCanvas = Object.assign(document.createElement('canvas'), { width: SCENE_PX, height: SCENE_PX });
const sceneCtx = sceneCanvas.getContext('2d');

const scene = new Scene();
const hud = new Hud();
const socket = new BackendSocket('/ws');
const prefs = loadPrefs();

let state = null;
let online = false;
let injectEnabled = false;

// ---------- backend events ----------
socket.addEventListener('open', () => { online = true; hud.setBackend(true); });
socket.addEventListener('close', () => { online = false; hud.setBackend(false); });
socket.addEventListener('hello', (e) => {
  hud.setHello(e.detail);
  injectEnabled = e.detail.inject;
  e.detail.log.forEach((entry) => hud.log(entry));
});
socket.addEventListener('state', (e) => { state = e.detail; hud.render(state); });
socket.addEventListener('log', (e) => hud.log(e.detail));
socket.connect();

// ---------- display controls ----------
const holo = () => root.dataset.mode === 'holo';
function setMode(mode) {
  root.dataset.mode = mode;
  $('btn-holo').setAttribute('aria-pressed', String(mode === 'holo'));
  resize();
}
function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen?.().catch(() => {});
}
function bindRange(id, outId, key, min, max, factor) {
  const input = $(id), out = $(outId);
  input.value = String(Math.round(prefs[key] * 100));
  const apply = () => {
    prefs[key] = Math.min(max, Math.max(min, Number(input.value) / 100));
    out.textContent = `${Math.round(prefs[key] * 100)}%`;
    savePrefs(prefs);
  };
  input.addEventListener('input', apply);
  apply();
  return (delta) => { input.value = String(Math.round(prefs[key] * 100 + delta * factor)); apply(); };
}
const nudgeScale = bindRange('in-scale', 'out-scale', 'scale', 0.15, 0.48, 1);
const nudgeGap = bindRange('in-gap', 'out-gap', 'gap', 0, 0.2, 1);
$('in-guide').checked = prefs.guide;
$('in-guide').addEventListener('change', (e) => { prefs.guide = e.target.checked; savePrefs(prefs); });

$('btn-holo').addEventListener('click', () => setMode(holo() ? 'control' : 'holo'));
$('btn-full').addEventListener('click', toggleFullscreen);
$('btn-on').addEventListener('click', () => socket.send({ type: 'command', cmd: 'LED_ON' }));
$('btn-off').addEventListener('click', () => socket.send({ type: 'command', cmd: 'LED_OFF' }));

// ---------- keyboard ----------
const INJECT = { Digit1: 'POINT', Digit2: 'THUMBS_UP', Digit3: 'OPEN_PALM' };
let injected = null;
addEventListener('keydown', (e) => {
  if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target instanceof HTMLInputElement && e.target.type === 'range') return;
  switch (e.code) {
    case 'KeyH': setMode(holo() ? 'control' : 'holo'); break;
    case 'KeyF': toggleFullscreen(); break;
    case 'KeyG': prefs.guide = !prefs.guide; $('in-guide').checked = prefs.guide; savePrefs(prefs); break;
    case 'Equal': case 'NumpadAdd': nudgeScale(+1); break;
    case 'Minus': case 'NumpadSubtract': nudgeScale(-1); break;
    case 'BracketRight': nudgeGap(+1); break;
    case 'BracketLeft': nudgeGap(-1); break;
    default:
      if (injectEnabled && INJECT[e.code]) {
        injected = e.code;
        socket.send({ type: 'inject', gesture: INJECT[e.code] });
      }
  }
});
addEventListener('keyup', (e) => {
  if (injectEnabled && injected === e.code) {
    injected = null;
    socket.send({ type: 'inject', gesture: 'NONE' });
  }
});

// ---------- rendering ----------
let cssW = 0, cssH = 0, dpr = 1;
function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = canvas.getBoundingClientRect();
  cssW = Math.max(1, r.width); cssH = Math.max(1, r.height);
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
}
new ResizeObserver(resize).observe(canvas);
resize();

let last = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  scene.update(dt, state, online);

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, cssW, cssH);

  if (holo()) {
    sceneCtx.clearRect(0, 0, SCENE_PX, SCENE_PX);
    scene.draw(sceneCtx, SCENE_PX, { compact: true });
    drawHologram(ctx, cssW, cssH, sceneCanvas, prefs);
  } else {
    const size = Math.min(cssW, cssH) * 0.96;
    ctx.save();
    ctx.translate((cssW - size) / 2, (cssH - size) / 2);
    scene.draw(ctx, size);
    ctx.restore();
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
