/* Движок воспроизведения.
   Один живой AudioContext: устройство вывода не засыпает, и первый слог клипа не глотается.
   Откуда звук: похвала — голос родителя, если записан; иначе голос автора; иначе голос модели.
   Файлы приходят по ссылкам /api/v1/media/…; service worker кладёт их в кеш для офлайна. */

import { getVoice, modelVoiceOn } from "./voices.js";
import { audioFor } from "./state.js";

let ac = null, rafId = 0, playing = null, playToken = null;

export function audioCtx(){
  if (!ac){
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    try { ac = new C(); } catch { return null; }
  }
  if (ac.state === "suspended") ac.resume().catch(() => {});
  return ac;
}
if (typeof document !== "undefined"){
  ["pointerdown", "keydown", "touchstart"].forEach(t =>
    document.addEventListener(t, () => audioCtx(), { capture: true, passive: true }));
}

export function b64ToBuffer(b64){
  const bin = atob(b64), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u.buffer;
}
export function speechBounds(buf){
  const d = buf.getChannelData(0), win = Math.max(1, Math.round(buf.sampleRate * 0.01));
  const rms = []; let peak = 0;
  for (let i = 0; i + win <= d.length; i += win){
    let s = 0; for (let j = 0; j < win; j++){ const v = d[i + j]; s += v * v; }
    const r = Math.sqrt(s / win); rms.push(r); if (r > peak) peak = r;
  }
  const th = peak * 0.06;
  let a = rms.findIndex(r => r > th), b = rms.length - 1;
  while (b > 0 && rms[b] <= th) b--;
  if (a < 0){ a = 0; b = rms.length - 1; }
  return { s: a * win / buf.sampleRate, e: (b + 1) * win / buf.sampleRate };
}

const bufCache = new Map();
const BUF_LIMIT = 80;          // держим в памяти не больше стольких раскодированных звуков

export function sourceFor(key){
  const rec = key.startsWith("p:") ? getVoice(key) : null;
  if (rec && (rec.wav || rec.url)) return { id: key + "@" + rec.at, b64: rec.wav, url: rec.url };
  const a = audioFor(key);
  if (a && a.url) return { id: a.url, url: a.url };
  if (a && a.model && modelVoiceOn()) return { id: a.model, url: a.model };
  return null;
}

/* Заранее скачиваем и раскодируем звуки урока: первое нажатие звучит сразу,
   а файлы оседают в кеше и работают без интернета. */
export function warm(keys){
  const list = keys.map(sourceFor).filter(Boolean);
  let chain = Promise.resolve();
  list.forEach(src => { chain = chain.then(() => getBuffer(src).catch(() => {})); });
  return chain;
}
export const hasAudio = key => !!sourceFor(key);

async function bytesOf(src){
  if (src.b64) return b64ToBuffer(src.b64);
  const res = await fetch(src.url);
  if (!res.ok) throw new Error("voice_fetch");
  return res.arrayBuffer();
}
function getBuffer(src){
  if (!bufCache.has(src.id)){
    const p = bytesOf(src).then(bytes => audioCtx().decodeAudioData(bytes)).then(buf => ({ buf, ...speechBounds(buf) }));
    p.catch(() => bufCache.delete(src.id));
    bufCache.set(src.id, p);
    if (bufCache.size > BUF_LIMIT) bufCache.delete(bufCache.keys().next().value);
  }
  return bufCache.get(src.id);
}

export function stopAudio(){
  playToken = null;
  if (playing){ const p = playing; playing = null; try { p.node.onended = null; p.node.stop(); } catch {} p.resolve(false); }
  cancelAnimationFrame(rafId);
  try { speechSynthesis.cancel(); } catch {}
}

function pickVoice(){
  try {
    const vs = speechSynthesis.getVoices();
    return vs.find(v => /^kk/i.test(v.lang)) || vs.find(v => /^ru/i.test(v.lang)) || null;
  } catch { return null; }
}
try { speechSynthesis.getVoices(); } catch {}

/* Проигрывает источник {id, b64|url}. null — источника нет или его не удалось декодировать. */
async function playSource(src, token, onProgress){
  const ctx = src ? audioCtx() : null;
  if (!src || !ctx) return null;
  let item = null;
  try { item = await getBuffer(src); } catch {}
  if (playToken !== token) return false;
  if (!item) return null;
  return new Promise(resolve => {
    const node = ctx.createBufferSource();
    node.buffer = item.buf; node.connect(ctx.destination);
    const t0 = ctx.currentTime + 0.05;
    node.start(t0);
    playing = { node, resolve };
    const tick = () => {
      if (!playing || playing.node !== node) return;
      const t = ctx.currentTime - t0;
      if (onProgress && t >= item.s) onProgress(Math.min(0.999, (t - item.s) / Math.max(0.08, item.e - item.s)));
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    node.onended = () => {
      if (playing && playing.node === node) playing = null;
      cancelAnimationFrame(rafId); onProgress && onProgress(1); resolve(true);
    };
  });
}

/* Файл по адресу (редактор автора). */
export async function playUrl(url){
  stopAudio();
  const token = {}; playToken = token;
  const done = await playSource({ id: url, url }, token);
  return done === true;
}

/* Запись ребёнка (WAV в base64): «послушай, как ты сказал». */
export async function playWav(b64, id){
  stopAudio();
  const token = {}; playToken = token;
  const done = await playSource({ id: id || "take@" + Date.now(), b64 }, token);
  return done === true;
}

export async function play(key, { onProgress } = {}){
  stopAudio();
  const token = {}; playToken = token;
  const src = sourceFor(key);
  const done = await playSource(src, token, onProgress);
  if (done !== null) return done;
  if (playToken !== token) return false;
  if (key.startsWith("w:") && modelVoiceOn() && "speechSynthesis" in window){
    return new Promise(resolve => {
      const u = new SpeechSynthesisUtterance(key.slice(2));
      const v = pickVoice();
      if (v){ u.voice = v; u.lang = v.lang; } else u.lang = "kk-KZ";
      u.rate = 0.85;
      const start = performance.now();
      const tick = () => { onProgress && onProgress(Math.min(0.999, (performance.now() - start) / 900)); rafId = requestAnimationFrame(tick); };
      u.onstart = () => { rafId = requestAnimationFrame(tick); };
      u.onend = u.onerror = () => { cancelAnimationFrame(rafId); onProgress && onProgress(1); resolve(true); };
      speechSynthesis.speak(u);
    });
  }
  return false;
}

