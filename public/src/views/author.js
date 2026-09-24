/* Редактор автора (/#author): категории, слова, запись голоса автора, картинки, фразы похвалы.
   Вход — пароль автора (ADMIN_PASSWORD на сервере). Токен автора хранится отдельно
   от токена семьи и уходит в заголовке X-Admin-Token. */

import { navigate, viewEl, currentGen, goAfterAuth } from "../main.js";
import { BASE, store } from "../api.js";
import { syncTopics } from "../state.js";
import { t } from "../i18n.js";
import { ICON, $, esc } from "../ui.js";
import { playUrl, stopAudio, audioCtx } from "../audio.js";
import { recordOnce, stopOnce, processTake } from "../recorder.js";

const K_TOKEN = "adminToken";
let cat = null;              // каталог автора: {topics, phrases}
let stats = null;
let tab = null;              // id категории | "phrases" | "new"
let busyKey = null;          // строка, которая сейчас пишет голос
let dirty = false;           // были правки — при выходе обновим каталог семьи

/* ---------- API автора ---------- */
class AuthorError extends Error { constructor(code, status){ super(code); this.code = code; this.status = status; } }

function token(){
  const tk = store.get(K_TOKEN, null);
  if (!tk || !tk.token || tk.exp < Date.now()) return null;
  return tk.token;
}

async function call(path, { method = "GET", body, form } = {}){
  const headers = { "Accept": "application/json" };
  const tk = token();
  if (tk) headers["X-Admin-Token"] = tk;
  let payload;
  if (form) payload = form;
  else if (body !== undefined){ headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try { res = await fetch(BASE + path, { method, headers, body: payload }); }
  catch { throw new AuthorError("offline", 0); }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok){
    const code = (data && data.detail) || "http_" + res.status;
    if (res.status === 401 && code === "admin_token_invalid"){ store.del(K_TOKEN); }
    throw new AuthorError(typeof code === "string" ? code : "http_" + res.status, res.status);
  }
  return data;
}
const upload = (path, blob, name) => { const fd = new FormData(); fd.append("file", blob, name); return call(path, { method: "PUT", form: fd }); };

const ERR = {
  offline: "err_network", password_invalid: "au_err_password", too_many_attempts: "err_too_many",
  admin_disabled: "au_err_disabled", admin_token_invalid: "au_err_session", file_too_large: "au_err_big",
  unsupported_media_type: "au_err_type", quiet: "err_quiet", decode: "err_decode",
  photos_disabled: "au_photo_off", photos_unavailable: "au_photo_err", photo_not_found: "au_photo_err"
};
const errText = e => t(ERR[e && e.code] || (e && e.name === "NotAllowedError" ? "err_mic_denied" : "err_save"));

/* ---------- вход/выход ---------- */
export function render(){
  if (!token()) return renderLogin();
  renderEditor();
}

export function leave(){
  stopOnce(); busyKey = null;
  if (dirty){ dirty = false; syncTopics(); }
}

function exitToSite(){
  history.replaceState(null, "", location.pathname + location.search);
  goAfterAuth();
}

function renderLogin(){
  viewEl().innerHTML = `
  <section class="home gate-wrap">
    <div class="gate patch">
      <p class="eyebrow">${t("au_eyebrow")}</p>
      <h2>${t("au_login_head")}</h2>
      <p class="note">${t("au_login_note")}</p>
      <form class="ai-form" id="f">
        <div class="ai-row">
          <label class="sr" for="pw">${t("au_password")}</label>
          <input id="pw" type="password" autocomplete="current-password" placeholder="${t("au_password")}">
          <button class="btn primary" id="go" type="submit">${t("au_login_btn")}${ICON.arrow}</button>
        </div>
        <p class="status" id="st"></p>
      </form>
      <div class="gate-foot">
        <button class="btn ghost small" id="back" type="button">${ICON.back}${t("au_to_site")}</button>
      </div>
    </div>
  </section>`;
  $("#pw").focus();
  $("#back").onclick = exitToSite;
  $("#f").onsubmit = async e => {
    e.preventDefault();
    const btn = $("#go"); btn.disabled = true; $("#st").textContent = "";
    try {
      const out = await call("/admin/login", { method: "POST", body: { password: $("#pw").value } });
      store.set(K_TOKEN, { token: out.token, exp: Date.now() + (out.expires_in - 60) * 1000 });
      cat = null;
      renderEditor();
    } catch (err){ $("#st").textContent = errText(err); btn.disabled = false; }
  };
}

/* ---------- редактор ---------- */
async function load(){
  const [c, s] = await Promise.all([call("/admin/catalog"), call("/admin/stats").catch(() => null)]);
  cat = c; stats = s;
}

async function renderEditor(){
  const g = currentGen();
  if (!cat){
    viewEl().innerHTML = `<section class="home"><p class="note">${t("au_loading")}</p></section>`;
    try { await load(); }
    catch (err){ if (g !== currentGen()) return; if (!token()) return renderLogin(); viewEl().innerHTML = `<section class="home"><p class="status">${esc(errText(err))}</p></section>`; return; }
    if (g !== currentGen()) return;
  }
  if (!tab || (tab !== "phrases" && tab !== "new" && !cat.topics.some(x => x.id === tab))) tab = cat.topics.length ? cat.topics[0].id : "new";
  paint();
}

function paint(){
  const topics = cat.topics;
  const voiced = tp => tp.words.filter(w => w.audio_url).length;
  const s = stats;
  viewEl().innerHTML = `
  <section class="author">
    <div class="lesson-bar">
      <button class="btn ghost small" id="toSite" type="button">${ICON.back}${t("au_to_site")}</button>
      <span></span>
      <button class="btn ghost small" id="logout" type="button">${t("au_logout")}</button>
    </div>

    <div class="studio-head patch">
      <div>
        <p class="eyebrow">${t("au_eyebrow")}</p>
        <h2>${t("au_head")}</h2>
        <p class="note">${t("au_note")}</p>
      </div>
      ${s ? `<dl class="au-stats">
        <div><dt>${t("au_st_families")}</dt><dd>${s.families}</dd></div>
        <div><dt>${t("au_st_active")}</dt><dd>${s.families_active_7d}</dd></div>
        <div><dt>${t("au_st_children")}</dt><dd>${s.children}</dd></div>
        <div><dt>${t("au_st_today")}</dt><dd>${s.attempts_today}</dd></div>
        <div><dt>${t("au_st_voice")}</dt><dd>${s.words_with_voice} / ${s.words}</dd></div>
        <div><dt>${t("au_st_space")}</dt><dd>${String(s.media_mb).replace(".", ",")} МБ</dd></div>
      </dl>` : ""}
    </div>

    <div class="tabs" role="tablist">
      ${topics.map(tp => `<button class="chip" type="button" data-tab="${esc(tp.id)}" aria-pressed="${tp.id === tab}">
        ${tp.is_published ? "" : `<span class="au-draft">${t("au_draft")}</span>`}${esc(tp.title_kk)}<small>${voiced(tp)}/${tp.words.length}</small></button>`).join("")}
      <button class="chip" type="button" data-tab="phrases" aria-pressed="${tab === "phrases"}">${t("au_phrases")}</button>
      <button class="chip au-add" type="button" data-tab="new" aria-pressed="${tab === "new"}">${ICON.plus}${t("au_new_topic")}</button>
    </div>

    <div id="panel"></div>
    <p class="status au-status" id="st" role="status"></p>
  </section>`;

  $("#toSite").onclick = exitToSite;
  $("#logout").onclick = () => { store.del(K_TOKEN); cat = null; renderLogin(); };
  viewEl().querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { if (busyKey) return; tab = b.dataset.tab; paint(); });

  if (tab === "new") paintNewTopic();
  else if (tab === "phrases") paintPhrases();
  else paintTopic(topics.find(x => x.id === tab));
}

const status = txt => { const el = $("#st"); if (el) el.textContent = txt || ""; };
const touch = () => { dirty = true; };

/* ---------- новая категория ---------- */
function paintNewTopic(){
  $("#panel").innerHTML = `
  <section class="patch au-panel">
    <h3 class="mh-sub">${t("au_new_topic")}</h3>
    <form class="au-grid" id="nt">
      <label>${t("au_title_kk")}<input id="ntKk" required maxlength="128"></label>
      <label>${t("au_title_ru")}<input id="ntRu" maxlength="128"></label>
      <label>${t("au_emoji")}<input id="ntPic" maxlength="8" placeholder="🚗"></label>
      <div class="au-row-actions"><button class="btn primary" type="submit">${t("au_create")}</button></div>
    </form>
    <p class="note">${t("au_new_topic_note")}</p>
  </section>`;
  $("#nt").onsubmit = async e => {
    e.preventDefault();
    try {
      const tp = await call("/admin/topics", { method: "POST", body: { title_kk: $("#ntKk").value, title_ru: $("#ntRu").value, pic: $("#ntPic").value } });
      cat.topics.push(tp); tab = tp.id; touch(); paint(); status(t("au_created"));
    } catch (err){ status(errText(err)); }
  };
}

/* ---------- категория ---------- */
function replaceTopic(tp){ const i = cat.topics.findIndex(x => x.id === tp.id); if (i >= 0) cat.topics[i] = tp; }
function replaceWord(topic, w){ const i = topic.words.findIndex(x => x.id === w.id); if (i >= 0) topic.words[i] = w; }

function picOf(item){
  if (item.image_url) return `<img class="wpic" src="${esc(item.image_url)}" alt="">`;
  return `<span class="emoji" aria-hidden="true">${esc(item.pic || "·")}</span>`;
}

function voiceState(item){
  if (item.audio_url) return t("au_voice_yours");
  if (item.model_audio_url) return t("au_voice_model");
  return t("au_voice_none");
}

function paintTopic(tp){
  if (!tp) return;
  const idx = cat.topics.indexOf(tp);
  $("#panel").innerHTML = `
  <section class="patch au-panel">
    <form class="au-grid" id="tf">
      <label>${t("au_title_kk")}<input id="tKk" value="${esc(tp.title_kk)}" maxlength="128"></label>
      <label>${t("au_title_ru")}<input id="tRu" value="${esc(tp.title_ru)}" maxlength="128"></label>
      <label>${t("au_emoji")}<input id="tPic" value="${esc(tp.pic)}" maxlength="16"></label>
      <label class="switch" for="tPub"><input type="checkbox" id="tPub" ${tp.is_published ? "checked" : ""}><span>${t("au_published")}</span></label>
    </form>
    <div class="au-topic-bar">
      <span class="plate au-plate">${tp.image_url ? `<img class="wpic" src="${esc(tp.image_url)}" alt="">` : `<span class="emoji">${esc(tp.pic || "·")}</span>`}</span>
      <button class="btn small" id="tPhoto" type="button">${t("au_photo")}</button>
      <label class="btn small" for="tImg"><input class="sr" type="file" accept="image/*" id="tImg">${t("au_image")}</label>
      ${tp.image_url ? `<button class="btn ghost small" id="tImgDel" type="button">${t("au_image_del")}</button>` : ""}
      <span class="au-spacer"></span>
      <button class="btn ghost small" id="tUp" type="button" ${idx <= 0 ? "disabled" : ""}>↑ ${t("au_move_left")}</button>
      <button class="btn ghost small" id="tDown" type="button" ${idx >= cat.topics.length - 1 ? "disabled" : ""}>↓ ${t("au_move_right")}</button>
      <button class="btn ghost small au-danger" id="tDel" type="button">${ICON.trash}${t("au_delete_topic")}</button>
    </div>
  </section>

  <ul class="rec-list au-words" id="words">
    ${tp.words.map((w, i) => wordRow(w, i, tp.words.length)).join("")}
  </ul>
  ${tp.words.length ? "" : `<p class="note">${t("au_no_words")}</p>`}

  <section class="patch au-panel">
    <h3 class="mh-sub">${t("au_add_word")}</h3>
    <form class="au-grid" id="aw">
      <label>${t("au_word")}<input id="awKk" required maxlength="64" lang="kk"></label>
      <label>${t("au_syll")}<input id="awSy" maxlength="96" placeholder="${t("au_syll_ph")}" lang="kk"></label>
      <label>${t("au_ru")}<input id="awRu" maxlength="64"></label>
      <label>${t("au_emoji")}<input id="awPic" maxlength="16"></label>
      <div class="au-row-actions"><button class="btn primary" type="submit">${ICON.plus}${t("au_add")}</button></div>
    </form>
    <details class="au-bulk">
      <summary>${t("au_bulk")}</summary>
      <p class="note">${t("au_bulk_note")}</p>
      <textarea id="bulk" rows="6" placeholder="алма; яблоко; ал-ма&#10;шие; вишня; ши-е" lang="kk"></textarea>
      <button class="btn" id="bulkGo" type="button">${t("au_bulk_btn")}</button>
    </details>
  </section>`;

  // поля категории сохраняем при уходе с поля
  const saveTopic = async patch => {
    try { const out = await call("/admin/topics/" + tp.id, { method: "PATCH", body: patch }); replaceTopic(out); touch(); status(t("au_saved")); paint(); }
    catch (err){ status(errText(err)); }
  };
  $("#tKk").onchange = e => saveTopic({ title_kk: e.target.value });
  $("#tRu").onchange = e => saveTopic({ title_ru: e.target.value });
  $("#tPic").onchange = e => saveTopic({ pic: e.target.value });
  $("#tPub").onchange = e => saveTopic({ is_published: e.target.checked });
  $("#tf").onsubmit = e => e.preventDefault();
  $("#tImg").onchange = async e => {
    const file = e.target.files && e.target.files[0]; if (!file) return;
    try { status(t("au_uploading")); const blob = await shrinkImage(file); replaceTopic(await upload("/admin/topics/" + tp.id + "/image", blob, "topic." + ext(blob))); touch(); paint(); status(t("au_saved")); }
    catch (err){ status(errText(err)); }
  };
  if ($("#tImgDel")) $("#tImgDel").onclick = async () => { try { replaceTopic(await call("/admin/topics/" + tp.id + "/image", { method: "DELETE" })); touch(); paint(); } catch (err){ status(errText(err)); } };
  const moveTopic = async d => {
    const ids = cat.topics.map(x => x.id); const i = ids.indexOf(tp.id);
    [ids[i], ids[i + d]] = [ids[i + d], ids[i]];
    try { cat = await call("/admin/topics/order", { method: "POST", body: { ids } }); touch(); paint(); } catch (err){ status(errText(err)); }
  };
  $("#tPhoto").onclick = () => photoPanel($("#tPhoto").closest("section"), { text_ru: tp.title_ru, text_kk: tp.title_kk },
    out => { replaceTopic(out); touch(); paint(); }, "/admin/topics/" + tp.id + "/image/pexels");
  $("#tUp").onclick = () => moveTopic(-1);
  $("#tDown").onclick = () => moveTopic(1);
  $("#tDel").onclick = async () => {
    const btn = $("#tDel");
    if (!btn.dataset.sure){ btn.dataset.sure = "1"; btn.innerHTML = ICON.trash + t("au_delete_sure"); status(t("au_delete_topic_warn", { n: tp.words.length })); return; }
    try { await call("/admin/topics/" + tp.id, { method: "DELETE" }); cat.topics = cat.topics.filter(x => x.id !== tp.id); tab = null; touch(); renderEditor(); status(t("au_deleted")); }
    catch (err){ status(errText(err)); }
  };

  $("#aw").onsubmit = async e => {
    e.preventDefault();
    const body = { text_kk: $("#awKk").value.trim(), syllables: $("#awSy").value.trim(), text_ru: $("#awRu").value.trim(), pic: $("#awPic").value.trim() };
    if (!body.text_kk) return;
    try { const w = await call("/admin/topics/" + tp.id + "/words", { method: "POST", body }); tp.words.push(w); touch(); paint(); status(t("au_word_added", { word: w.text_kk })); $("#awKk") && $("#awKk").focus(); }
    catch (err){ status(errText(err)); }
  };
  $("#bulkGo").onclick = async () => {
    const words = parseBulk($("#bulk").value);
    if (!words.length){ status(t("au_bulk_empty")); return; }
    const before = tp.words.length;
    try { const out = await call("/admin/topics/" + tp.id + "/words/bulk", { method: "POST", body: { words } }); replaceTopic(out); touch(); paint(); status(t("au_bulk_done", { n: out.words.length - before })); }
    catch (err){ status(errText(err)); }
  };

  $("#words").querySelectorAll(".rec-row").forEach(row => wireWordRow(tp, row));
}

function wordRow(w, i, n){
  return `<li class="rec-row au-row${w.audio_url ? " has" : ""}" data-id="${esc(w.id)}">
    <span class="plate au-plate">${picOf(w)}</span>
    <span class="au-fields">
      <input data-f="text_kk" value="${esc(w.text_kk)}" aria-label="${t("au_word")}" lang="kk" class="au-word">
      <input data-f="syllables" value="${esc(w.syllables)}" aria-label="${t("au_syll")}" lang="kk">
      <input data-f="text_ru" value="${esc(w.text_ru)}" aria-label="${t("au_ru")}" placeholder="${t("au_ru")}">
      <input data-f="pic" value="${esc(w.pic)}" aria-label="${t("au_emoji")}" class="au-emoji">
      <small class="au-voice">${voiceState(w)}${w.image_credit ? " · " + esc(w.image_credit) : ""}</small>
    </span>
    <span class="rec-actions">
      <button class="btn rec-btn" type="button" data-act="rec">${ICON.mic}${w.audio_url ? t("au_rerecord") : t("rec_btn")}</button>
      <button class="icon-btn" type="button" data-act="play" aria-label="${t("btn_listen")}" ${w.audio_url || w.model_audio_url ? "" : "disabled"}>${ICON.play}</button>
      <label class="icon-btn" title="${t("rec_file_title")}"><input class="sr" type="file" accept="audio/*" data-act="afile">${ICON.upload}</label>
      <button class="icon-btn" type="button" data-act="adel" aria-label="${t("au_voice_del")}" title="${t("au_voice_del")}" ${w.audio_url ? "" : "disabled"}>${ICON.trash}</button>
      <button class="btn small" type="button" data-act="photo">${t("au_photo")}</button>
      <label class="btn small" title="${t("au_image")}"><input class="sr" type="file" accept="image/*" data-act="img">${t("au_image")}</label>
      ${w.image_url ? `<button class="btn ghost small" type="button" data-act="imgdel">${t("au_image_del")}</button>` : ""}
      <button class="icon-btn" type="button" data-act="up" aria-label="↑" ${i === 0 ? "disabled" : ""}>↑</button>
      <button class="icon-btn" type="button" data-act="down" aria-label="↓" ${i === n - 1 ? "disabled" : ""}>↓</button>
      <button class="btn ghost small au-danger" type="button" data-act="del">${t("au_delete_word")}</button>
    </span>
  </li>`;
}

function wireWordRow(tp, row){
  const id = row.dataset.id;
  const w = () => tp.words.find(x => x.id === id);
  const q = a => row.querySelector(`[data-act="${a}"]`);
  const refresh = out => { replaceWord(tp, out); touch(); paint(); };

  row.querySelectorAll("input[data-f]").forEach(inp => inp.onchange = async () => {
    try { refresh(await call("/admin/words/" + id, { method: "PATCH", body: { [inp.dataset.f]: inp.value } })); status(t("au_saved")); }
    catch (err){ status(errText(err)); }
  });
  q("play").onclick = () => { const x = w(); playUrl(x.audio_url || x.model_audio_url); };
  q("rec").onclick = () => recordFor(id, row, async wavB64 => refresh(await upload("/admin/words/" + id + "/audio", wavBlob(wavB64), "word.wav")), () => w().audio_url);
  q("afile").onchange = async e => {
    const file = e.target.files && e.target.files[0]; if (!file) return;
    try { status(t("rec_file_working")); const wav = await fileToWav(file); const out = await upload("/admin/words/" + id + "/audio", wavBlob(wav), "word.wav"); refresh(out); status(t("rec_file_saved")); playUrl(out.audio_url); }
    catch (err){ status(errText(err)); }
  };
  q("adel").onclick = async () => { try { refresh(await call("/admin/words/" + id + "/audio", { method: "DELETE" })); status(t("rec_deleted")); } catch (err){ status(errText(err)); } };
  q("img").onchange = async e => {
    const file = e.target.files && e.target.files[0]; if (!file) return;
    try { status(t("au_uploading")); const blob = await shrinkImage(file); refresh(await upload("/admin/words/" + id + "/image", blob, "word." + ext(blob))); status(t("au_saved")); }
    catch (err){ status(errText(err)); }
  };
  if (q("imgdel")) q("imgdel").onclick = async () => { try { refresh(await call("/admin/words/" + id + "/image", { method: "DELETE" })); } catch (err){ status(errText(err)); } };
  q("photo").onclick = () => photoPanel(row, w(), out => refresh(out), "/admin/words/" + id + "/image/pexels");
  const move = async d => {
    const ids = tp.words.map(x => x.id); const i = ids.indexOf(id);
    [ids[i], ids[i + d]] = [ids[i + d], ids[i]];
    try { replaceTopic(await call("/admin/topics/" + tp.id + "/words/order", { method: "POST", body: { ids } })); touch(); paint(); } catch (err){ status(errText(err)); }
  };
  q("up").onclick = () => move(-1);
  q("down").onclick = () => move(1);
  q("del").onclick = async () => {
    const btn = q("del");
    if (!btn.dataset.sure){ btn.dataset.sure = "1"; btn.textContent = t("au_delete_sure"); return; }
    try { await call("/admin/words/" + id, { method: "DELETE" }); tp.words = tp.words.filter(x => x.id !== id); touch(); paint(); status(t("au_deleted")); }
    catch (err){ status(errText(err)); }
  };
}

/* ---------- фразы похвалы ---------- */
function paintPhrases(){
  $("#panel").innerHTML = `
  <section class="patch au-panel">
    <p class="note">${t("au_phrases_note")}</p>
  </section>
  <ul class="rec-list au-words" id="phr">
    ${cat.phrases.map(p => `<li class="rec-row au-row${p.audio_url ? " has" : ""}" data-key="${esc(p.key)}">
      <span class="plate au-plate"><span class="quote">«»</span></span>
      <span class="au-fields">
        <input data-f="text_kk" value="${esc(p.text_kk)}" aria-label="${t("au_title_kk")}" lang="kk" class="au-word">
        <input data-f="text_ru" value="${esc(p.text_ru)}" aria-label="${t("au_title_ru")}">
        <small class="au-voice">${voiceState(p)}</small>
      </span>
      <span class="rec-actions">
        <button class="btn rec-btn" type="button" data-act="rec">${ICON.mic}${p.audio_url ? t("au_rerecord") : t("rec_btn")}</button>
        <button class="icon-btn" type="button" data-act="play" aria-label="${t("btn_listen")}" ${p.audio_url || p.model_audio_url ? "" : "disabled"}>${ICON.play}</button>
        <label class="icon-btn" title="${t("rec_file_title")}"><input class="sr" type="file" accept="audio/*" data-act="afile">${ICON.upload}</label>
        <button class="icon-btn" type="button" data-act="adel" aria-label="${t("au_voice_del")}" ${p.audio_url ? "" : "disabled"}>${ICON.trash}</button>
      </span>
    </li>`).join("")}
  </ul>
  ${cat.phrases.length ? "" : `<p class="note">${t("au_no_phrases")}</p>`}`;

  $("#phr").querySelectorAll(".rec-row").forEach(row => {
    const key = row.dataset.key;
    const p = () => cat.phrases.find(x => x.key === key);
    const q = a => row.querySelector(`[data-act="${a}"]`);
    const path = "/admin/phrases/" + encodeURIComponent(key);
    const refresh = out => { const i = cat.phrases.findIndex(x => x.key === key); cat.phrases[i] = out; touch(); paint(); };
    row.querySelectorAll("input[data-f]").forEach(inp => inp.onchange = async () => {
      try { refresh(await call(path, { method: "PATCH", body: { [inp.dataset.f]: inp.value } })); status(t("au_saved")); } catch (err){ status(errText(err)); }
    });
    q("play").onclick = () => playUrl(p().audio_url || p().model_audio_url);
    q("rec").onclick = () => recordFor(key, row, async wav => refresh(await upload(path + "/audio", wavBlob(wav), "phrase.wav")), () => p().audio_url);
    q("afile").onchange = async e => {
      const file = e.target.files && e.target.files[0]; if (!file) return;
      try { const wav = await fileToWav(file); const out = await upload(path + "/audio", wavBlob(wav), "phrase.wav"); refresh(out); playUrl(out.audio_url); } catch (err){ status(errText(err)); }
    };
    q("adel").onclick = async () => { try { refresh(await call(path + "/audio", { method: "DELETE" })); } catch (err){ status(errText(err)); } };
  });
}

/* ---------- поиск фотографии ----------
   Ключ Pexels живёт на сервере: клиент отправляет только слово и номер выбранного снимка. */
async function photoPanel(host, item, onPicked, pickPath){
  const old = host.querySelector(".au-photos");
  if (old){ old.remove(); return; }
  const box = document.createElement("div");
  box.className = "au-photos";
  box.innerHTML = `
    <div class="ai-row">
      <input class="au-q" aria-label="${t("au_photo_search")}" placeholder="${t("au_photo_search")}">
      <button class="btn small" type="button" data-go="1">${t("au_photo_find")}</button>
      <button class="btn small ghost" type="button" data-close="1">${t("au_photo_close")}</button>
    </div>
    <p class="note au-photo-note">${t("au_photo_hint")}</p>
    <div class="au-grid-photos"></div>`;
  host.appendChild(box);
  const input = box.querySelector(".au-q");
  const grid = box.querySelector(".au-grid-photos");
  const note = box.querySelector(".au-photo-note");
  input.value = (item.text_ru || item.text_kk || "").trim();
  input.focus();

  const find = async () => {
    const q = input.value.trim();
    if (!q) return;
    note.textContent = t("au_photo_looking");
    grid.innerHTML = "";
    let list = [];
    try { list = await call("/admin/photos?q=" + encodeURIComponent(q)); }
    catch (err){ note.textContent = errText(err); return; }
    if (!list.length){ note.textContent = t("au_photo_none"); return; }
    note.textContent = t("au_photo_pick");
    grid.innerHTML = list.map(p => `
      <button class="au-photo" type="button" data-id="${p.id}" title="${esc(p.photographer)}">
        <img src="${esc(p.thumb)}" alt="${esc(p.alt)}" loading="lazy">
        <small>${esc(p.photographer)}</small>
      </button>`).join("");
    grid.querySelectorAll(".au-photo").forEach(btn => btn.onclick = async () => {
      note.textContent = t("au_uploading");
      try {
        const out = await call(pickPath, { method: "POST", body: { photo_id: +btn.dataset.id } });
        box.remove();
        onPicked(out);
        status(t("au_saved"));
      } catch (err){ note.textContent = errText(err); }
    });
  };
  box.querySelector("[data-go]").onclick = find;
  box.querySelector("[data-close]").onclick = () => box.remove();
  input.onkeydown = e => { if (e.key === "Enter"){ e.preventDefault(); find(); } };
  find();
}

/* ---------- запись голоса ---------- */
async function recordFor(key, row, save, urlAfter){
  if (busyKey){ if (busyKey === key) stopOnce(); return; }
  stopAudio();
  const btn = row.querySelector('[data-act="rec"]');
  busyKey = key;
  row.classList.add("recording");
  btn.innerHTML = ICON.stop + t("rec_stop");
  status(t("rec_saying"));
  try {
    const rec = await recordOnce({ onLevel: rms => btn.style.setProperty("--lvl", Math.min(1, Math.sqrt(rms) * 2.6).toFixed(2)) });
    busyKey = null;
    status(t("rec_saving"));
    await save(rec.wav);
    status(t("rec_saved"));
    const url = urlAfter();
    if (url) playUrl(url);
  } catch (err){
    busyKey = null;
    row.classList.remove("recording");
    btn.innerHTML = ICON.mic + t("rec_btn");
    status(errText(err));
  }
}

/* ---------- файлы ---------- */
function wavBlob(b64){
  const bin = atob(b64), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return new Blob([u], { type: "audio/wav" });
}

async function fileToWav(file){
  const ctx = audioCtx();
  let buf;
  try { buf = await ctx.decodeAudioData(await file.arrayBuffer()); } catch { throw { code: "decode" }; }
  const mono = new Float32Array(buf.length);
  for (let c = 0; c < buf.numberOfChannels; c++){ const d = buf.getChannelData(c); for (let i = 0; i < d.length; i++) mono[i] += d[i] / buf.numberOfChannels; }
  return (await processTake(mono, buf.sampleRate)).wav;
}

const ext = blob => ({ "image/webp": "webp", "image/jpeg": "jpg", "image/png": "png" }[blob.type] || "png");

/* Картинку уменьшаем до 512 px и сжимаем: на телефоне ребёнка она грузится мгновенно. */
async function shrinkImage(file, max = 512){
  let bitmap;
  try { bitmap = await createImageBitmap(file); }
  catch {
    const url = URL.createObjectURL(file);
    bitmap = await new Promise((res, rej) => { const img = new Image(); img.onload = () => res(img); img.onerror = () => rej({ code: "unsupported_media_type" }); img.src = url; });
  }
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale)), h = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  canvas.getContext("2d").drawImage(bitmap, 0, 0, w, h);
  const toBlob = (type, q) => new Promise(res => canvas.toBlob(res, type, q));
  let blob = await toBlob("image/webp", 0.86);
  if (!blob || blob.type !== "image/webp") blob = await toBlob("image/png");       // прозрачный фон сохраняем
  if (blob && blob.size > 900 * 1024) blob = await toBlob("image/jpeg", 0.85);
  if (!blob) throw { code: "unsupported_media_type" };
  return blob;
}

/* «слово; перевод; слоги» — по строке на слово. Разделитель: ; или табуляция (вставка из таблицы). */
function parseBulk(text){
  return String(text || "").split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
    const parts = line.split(/\t|;/).map(x => x.trim());
    return { text_kk: parts[0] || "", text_ru: parts[1] || "", syllables: parts[2] || "", pic: parts[3] || "" };
  }).filter(x => x.text_kk).slice(0, 200);
}
