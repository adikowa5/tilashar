/* Записи похвалы голосом родителя («Керемет!», «Жарайсың!» …).
   Слова уроков озвучивает автор — их семья не записывает.
   Источник истины — API (/voices); без сети работает локальный IndexedDB-фолбэк. */

import { api, hasSession, isOnline } from "./api.js";
import { state, setSetting } from "./state.js";

/* key -> {key, wav?(base64), url?, dur, at} */
export const VOICES = new Map();
export const voiceStore = { kind: "pending" };          // "api" | "idb" | "memory"

const voiceListeners = new Set();
export function onVoices(fn){ voiceListeners.add(fn); return () => voiceListeners.delete(fn); }
export const emitVoices = () => voiceListeners.forEach(f => { try { f(); } catch {} });

export const keyToId = key => [...key].map(c => /[A-Za-z0-9_]/.test(c) ? c : "~" + c.codePointAt(0).toString(16)).join("");

/* ---------- фразы похвалы и полный список ключей ---------- */
export const PHRASE_KEYS = [
  "p:your_turn", "p:great", "p:good", "p:almost",
  "p:again", "p:silent", "p:mic_intro", "p:done"
];
export const voiceKeys = () => PHRASE_KEYS.slice();
export const recordedCount = keys => keys.filter(k => VOICES.has(k)).length;
export const getVoice = key => VOICES.get(key) || null;

/* ---------- IndexedDB ---------- */
function openIDB(){
  return new Promise((res, rej) => {
    const r = indexedDB.open("tilashar", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("voices", { keyPath: "key" });
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
function idb(mode, fn){
  return new Promise((res, rej) => {
    const tx = voiceStore.idb.transaction("voices", mode);
    const req = fn(tx.objectStore("voices"));
    tx.oncomplete = () => res(req && req.result);
    tx.onerror = () => rej(tx.error);
  });
}
async function ensureIDB(){
  if (voiceStore.idb) return true;
  try { voiceStore.idb = await openIDB(); return true; } catch { return false; }
}

/* ---------- инициализация ---------- */
export async function initVoices(){
  const local = await ensureIDB();
  if (local){
    try { (await idb("readonly", s => s.getAll())).forEach(v => { if (v && String(v.key).startsWith("p:")) VOICES.set(v.key, v); }); } catch {}
    voiceStore.kind = "idb";
  } else {
    voiceStore.kind = "memory";
  }
  emitVoices();
  await syncVoices();
}

/* Подтягиваем список с сервера: записи с url перекрывают локальные копии. */
export async function syncVoices(){
  if (!hasSession() || !isOnline()) return false;
  try {
    const list = await api.voices();
    if (!Array.isArray(list)) return false;
    const seen = new Set();
    list.forEach(v => {
      if (!v || typeof v.key !== "string" || !v.key.startsWith("p:")) return;
      seen.add(v.key);
      const prev = VOICES.get(v.key);
      VOICES.set(v.key, {
        key: v.key,
        url: v.url,
        wav: prev && prev.wav ? prev.wav : undefined,
        dur: typeof v.duration_ms === "number" ? Math.round(v.duration_ms / 100) / 10 : (prev ? prev.dur : 0),
        at: v.updated_at ? Date.parse(v.updated_at) || Date.now() : Date.now()
      });
    });
    // записи, которых на сервере нет, но есть локально, остаются — они ещё не ушли
    voiceStore.kind = "api";
    emitVoices();
    return true;
  } catch { return false; }
}

/* ---------- запись/удаление ---------- */
function wavBlob(b64){
  const bin = atob(b64), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return new Blob([u], { type: "audio/wav" });
}

export async function saveVoice(key, rec){
  const doc = Object.assign({ key }, rec);              // {wav, dur, at}
  let remoteErr = null;
  if (hasSession() && isOnline()){
    try {
      const saved = await api.putVoice(key, wavBlob(rec.wav), keyToId(key) + ".wav");
      if (saved && saved.url) doc.url = saved.url;
      voiceStore.kind = "api";
    } catch (e){ remoteErr = e; }
  }
  if (voiceStore.idb){ try { await idb("readwrite", s => s.put(doc)); } catch (e){ if (remoteErr) throw { code: "quota_exceeded" }; } }
  VOICES.set(key, doc);
  emitVoices();
  return doc;
}

export async function deleteVoice(key){
  if (hasSession() && isOnline()){ try { await api.delVoice(key); } catch {} }
  if (voiceStore.idb){ try { await idb("readwrite", s => s.delete(key)); } catch {} }
  VOICES.delete(key);
  emitVoices();
}

/* Переключатель модельного голоса живёт в настройках семьи. */
export const modelVoiceOn = () => state.settings.modelVoice !== false;
export async function setModelVoice(on){
  await setSetting("modelVoice", !!on);
  emitVoices();
}
