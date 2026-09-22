/* Студия родителя: только фразы похвалы («Керемет!», «Жарайсың!» …).
   Слова уроков озвучивает автор в редакторе (#author). Записи — voices.js (API + IndexedDB). */

import { navigate, viewEl, currentView } from "../main.js";
import { t } from "../i18n.js";
import { ICON, $, esc } from "../ui.js";
import { play, stopAudio, audioCtx, hasAudio } from "../audio.js";
import { Rec, processTake } from "../recorder.js";
import {
  VOICES, voiceStore, voiceKeys, recordedCount, keyToId,
  saveVoice, deleteVoice, onVoices, PHRASE_KEYS
} from "../voices.js";

let take = { key: null };
let unVoices = null;

export function leave(){
  if (Rec.open) Rec.close();
  take = { key: null };
  if (unVoices){ unVoices(); unVoices = null; }
}

function micErrorText(e){
  const n = e && e.name;
  if (n === "NotAllowedError" || n === "SecurityError") return t("err_mic_denied");
  if (n === "NotFoundError") return t("err_mic_missing");
  return t("err_mic_other");
}
function saveErrorText(e){
  const c = e && e.code;
  if (c === "quiet") return t("err_quiet");
  if (c === "quota_exceeded") return t("err_quota");
  if (c === "invalid_argument") return t("err_invalid");
  if (c === "decode") return t("err_decode");
  return t("err_save");
}

export function render(params = {}){
  // Студия — только через «взрослую дверь», чтобы ребёнок не перезаписал похвалу.
  if (!params.unlocked) return navigate("parent", { next: "studio" });
  const view = viewEl();
  const storeNote = { api: t("store_db"), idb: t("store_idb"), memory: t("store_memory"), pending: "" }[voiceStore.kind];

  view.innerHTML = `
  <section class="studio">
    <div class="lesson-bar">
      <button class="btn ghost small" id="home" type="button">${ICON.back}${t("back_home")}</button>
      <span></span>
      <span class="count" id="recTotal"></span>
    </div>
    <div class="studio-head patch">
      <div>
        <p class="eyebrow">${t("parent_eyebrow")}</p>
        <h2>${t("studio_head")}</h2>
        <p class="note">${t("studio_note_1")}</p>
        <p class="note">${t("studio_note_2")}</p>
      </div>
      <div class="studio-ctrl">
        <p class="mic-state" id="micState"><span class="led"></span><span id="micText">${t("mic_off")}</span></p>
        <div class="level" aria-hidden="true"><i id="lvl"></i></div>
        <p class="note" id="storeNote">${esc(storeNote)}</p>
        <p class="status" id="studioStatus" role="status"></p>
      </div>
    </div>
    <ul class="rec-list" id="recList"></ul>
  </section>`;

  $("#home").onclick = () => navigate("today");
  renderBody();

  if (unVoices) unVoices();
  unVoices = onVoices(() => {
    if (currentView() !== "studio" || take.key) return;
    renderBody();
    const n = $("#storeNote");
    if (n && !n.textContent && voiceStore.kind !== "pending") render({ unlocked: true });
  });
}

function renderBody(){
  if (currentView() !== "studio") return;
  const allKeys = voiceKeys();
  $("#recTotal").textContent = `${recordedCount(allKeys)} / ${allKeys.length} ${t("recorded_suffix")}`;
  const rows = PHRASE_KEYS.map(key => ({
    key, label: t("phrase_" + key), phrase: true,
    pic: `<span class="plate" style="--tint:var(--t-custom)"><span class="quote">«»</span></span>`
  }));

  const list = $("#recList");
  list.innerHTML = rows.map(r => {
    const rec = VOICES.get(r.key), id = keyToId(r.key);
    return `<li class="rec-row${rec ? " has" : ""}${r.phrase ? " phrase" : ""}" data-key="${esc(r.key)}">
      ${r.pic}
      <span class="rec-word"><b lang="kk">${esc(r.label)}</b><small>${rec ? esc(t("rec_done", { dur: String(rec.dur).replace(".", ",") })) : t("rec_none")}</small></span>
      <span class="rec-actions">
        <button class="btn rec-btn" type="button" data-act="rec">${ICON.mic}${t("rec_btn")}</button>
        <button class="icon-btn" type="button" data-act="play" aria-label="${esc(t("rec_listen_aria", { label: r.label }))}"${rec || hasAudio(r.key) ? "" : " disabled"}>${ICON.play}</button>
        <label class="icon-btn" for="f-${id}" title="${t("rec_file_title")}"><input class="sr" type="file" accept="audio/*" id="f-${id}" data-act="file">${ICON.upload}<span class="sr">${esc(t("rec_file_aria", { label: r.label }))}</span></label>
        <button class="icon-btn" type="button" data-act="del" aria-label="${esc(t("rec_del_aria", { label: r.label }))}"${rec ? "" : " disabled"}>${ICON.trash}</button>
      </span>
    </li>`;
  }).join("");

  list.querySelectorAll(".rec-row").forEach(row => {
    const key = row.dataset.key;
    row.querySelector('[data-act="rec"]').onclick = () => onRecord(key, row);
    row.querySelector('[data-act="play"]').onclick = () => { if (!take.key) play(key); };
    row.querySelector('[data-act="del"]').onclick = async () => {
      if (take.key) return;
      try { await deleteVoice(key); status(t("rec_deleted")); } catch (e){ status(saveErrorText(e)); }
    };
    row.querySelector('[data-act="file"]').onchange = e => onFile(key, e.target.files && e.target.files[0]);
  });
}

const status = txt => { const el = $("#studioStatus"); if (el) el.textContent = txt; };
function micUi(on){
  const st = $("#micState"); if (!st) return;
  st.classList.toggle("on", on);
  $("#micText").textContent = on ? t("mic_on") : t("mic_off");
  if (!on){ const l = $("#lvl"); if (l) l.style.width = "0"; }
}

async function onRecord(key, row){
  if (take.key){ if (take.key === key) finishTake(); return; }
  stopAudio();
  const btn = row.querySelector('[data-act="rec"]');
  btn.disabled = true;
  try { await Rec.start(); }
  catch (e){ btn.disabled = false; micUi(false); status(micErrorText(e)); return; }
  if (currentView() !== "studio"){ Rec.close(); return; }
  micUi(true);
  Rec.onLevel = rms => { const l = $("#lvl"); if (l) l.style.width = Math.min(100, Math.round(Math.sqrt(rms) * 260)) + "%"; };
  take = { key, done: false };
  row.classList.add("recording");
  row.querySelector("small").textContent = t("rec_saying");
  btn.disabled = false; btn.innerHTML = ICON.stop + t("rec_stop");
  status("");
  Rec.onAuto = () => finishTake();
  Rec.take();
}

async function finishTake(){
  if (!take.key || take.done) return;
  take.done = true;
  Rec.onAuto = null;
  const key = take.key, raw = Rec.finish();
  const view = viewEl();
  const row = view.querySelector(`.rec-row[data-key="${CSS.escape(key)}"]`);
  if (row){ row.classList.remove("recording"); row.querySelector("small").textContent = t("rec_saving"); }
  try {
    const rec = await processTake(raw.data, raw.sampleRate);
    await saveVoice(key, { wav: rec.wav, dur: rec.dur, at: Date.now() });
    take = { key: null };
    renderBody();
    status(t("rec_saved"));
    await play(key);
    const next = [...view.querySelectorAll(".rec-row:not(.has)")][0];
    if (next) next.querySelector('[data-act="rec"]').focus({ preventScroll: false });
  } catch (e){
    take = { key: null };
    renderBody();
    status(saveErrorText(e));
  }
}

async function onFile(key, file){
  if (!file || take.key) return;
  status(t("rec_file_working"));
  try {
    const ctx = audioCtx();
    let buf;
    try { buf = await ctx.decodeAudioData(await file.arrayBuffer()); } catch { throw { code: "decode" }; }
    const mono = new Float32Array(buf.length);
    for (let c = 0; c < buf.numberOfChannels; c++){ const d = buf.getChannelData(c); for (let i = 0; i < d.length; i++) mono[i] += d[i] / buf.numberOfChannels; }
    const rec = await processTake(mono, buf.sampleRate);
    await saveVoice(key, { wav: rec.wav, dur: rec.dur, at: Date.now() });
    status(t("rec_file_saved"));
    play(key);
  } catch (e){ status(saveErrorText(e)); }
}
