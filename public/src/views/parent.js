/* Родительская зона: дети, код семьи, язык интерфейса, голос модели, запись похвалы.
   Вход — через «взрослую дверь»: задача на умножение. */

import { navigate, viewEl, openMicHelp } from "../main.js";
import { state, setSetting, setActiveChild, signOut, syncMe } from "../state.js";
import { api, hasSession, isOnline } from "../api.js";
import { t, setLocale } from "../i18n.js";
import { ICON, $, esc, avatarHTML } from "../ui.js";
import { modelVoiceOn, setModelVoice } from "../voices.js";

let unlocked = false;
let gate = null;
let opts = {};

export function leave(){ unlocked = false; gate = null; }

function newGate(){
  const a = 3 + Math.floor(Math.random() * 7);   // 3..9
  const b = 3 + Math.floor(Math.random() * 7);
  return { a, b, answer: a * b };
}

export function render(params = {}){
  opts = params || {};
  if (!unlocked){ gate = gate || newGate(); return renderGate(); }
  afterUnlock();
}

function afterUnlock(){
  if (opts.next){ const next = opts.next; opts = {}; return navigate(next, { unlocked: true }); }
  renderZone();
}

function renderGate(){
  viewEl().innerHTML = `
  <section class="home gate-wrap">
    <div class="gate patch">
      <p class="eyebrow">${t("pz_eyebrow")}</p>
      <h2>${t("pz_gate_head")}</h2>
      <p class="note">${t("pz_gate_note")}</p>
      <form class="ai-form" id="f">
        <div class="ai-row">
          <label class="sr" for="ans">${esc(t("pz_gate_q", { a: gate.a, b: gate.b }))}</label>
          <span class="gate-q" aria-hidden="true">${esc(t("pz_gate_q", { a: gate.a, b: gate.b }))}</span>
          <input id="ans" inputmode="numeric" maxlength="4" autocomplete="off">
          <button class="btn primary" type="submit">${t("pz_gate_ok")}${ICON.arrow}</button>
        </div>
        <p class="status" id="st"></p>
      </form>
      <div class="gate-foot">
        <button class="btn ghost small" id="back" type="button">${ICON.back}${t("back")}</button>
      </div>
    </div>
  </section>`;
  $("#ans").focus();
  $("#f").onsubmit = e => {
    e.preventDefault();
    if (+$("#ans").value.trim() === gate.answer){ unlocked = true; afterUnlock(); }
    else { $("#st").textContent = t("pz_gate_wrong"); gate = newGate(); render(); }
  };
  $("#back").onclick = () => navigate("today");
}

function langRow(id, current){
  return `<div class="chips" id="${id}">
    ${["kk", "ru"].map(l => `<button class="chip" type="button" data-lang="${l}" aria-pressed="${l === current}">${t(l === "kk" ? "pz_lang_kk" : "pz_lang_ru")}</button>`).join("")}
  </div>`;
}

function renderZone(){
  const view = viewEl();
  const kids = state.children || [];
  view.innerHTML = `
  <section class="home">
    <div class="lesson-bar">
      <button class="btn ghost small" id="back" type="button">${ICON.back}${t("back_home")}</button>
      <span></span>
      <span class="count">${t("pz_eyebrow")}</span>
    </div>
    <div class="studio-head patch">
      <div>
        <p class="eyebrow">${t("pz_eyebrow")}</p>
        <h2>${t("pz_head")}</h2>
      </div>
      <div class="studio-ctrl">
        <label class="switch" for="mv"><input type="checkbox" id="mv" ${modelVoiceOn() ? "checked" : ""}><span>${t("pz_model_voice")}</span></label>
        <button class="btn red" id="toStudio" type="button">${ICON.mic}${t("pz_voice_studio")}</button>
        <button class="btn ghost" id="toMicHelp" type="button">${t("pz_mic_help")}</button>
        ${hasSession() ? `<button class="btn ghost" id="logout" type="button">${t("pz_logout")}</button>` : ""}
        <p class="note" id="logoutNote" hidden>${t("pz_logout_warn")}</p>
        <p class="status" id="st"></p>
      </div>
    </div>

    ${hasSession() ? `<section class="ai-band patch code-band" id="codeBand">
      <div>
        <p class="eyebrow">${t("pz_eyebrow")}</p>
        <h2>${t("pz_code_head")}</h2>
        <p class="note">${t("pz_code_note")}</p>
      </div>
      <div class="code-side">
        <p class="family-code" id="famCode" aria-live="polite">····-····</p>
        <div class="ai-row">
          <button class="btn" id="copyCode" type="button">${t("pz_code_copy")}</button>
          <button class="btn" id="shareCode" type="button">${t("pz_code_share")}</button>
        </div>
        <div class="ai-row">
          <button class="btn ghost small" id="newCode" type="button">${t("pz_code_new")}</button>
          <button class="btn ghost small" id="joinOther" type="button">${t("pz_code_join")}</button>
        </div>
        <p class="status" id="codeSt"></p>
      </div>
    </section>` : ""}

    <div class="section-head"><h2>${t("pz_children")}</h2></div>
    <div class="kids kids-grid">
      ${kids.map(c => `<button class="kid" type="button" data-id="${esc(c.id)}" aria-pressed="${c.id === state.activeChildId}">
        <span class="plate" style="--tint:var(--t-animals)">${avatarHTML(c.avatar)}</span>
        <b>${esc(c.name)}</b>
        <small>${esc(t("ch_years", { n: c.age }))} · ${esc(t("ch_stars", { n: c.stars_total || 0 }))}</small>
      </button>`).join("")}
      <button class="kid add" type="button" id="addKid">
        <span class="plate" style="--tint:var(--t-custom)">${ICON.plus}</span>
        <b>${t("ch_add")}</b>
      </button>
    </div>

    <section class="ai-band patch">
      <div>
        <p class="eyebrow">${t("pz_eyebrow")}</p>
        <h2>${t("pz_child_lang")}</h2>
        ${langRow("childLang", state.settings.childLocale || "kk")}
      </div>
      <div>
        <h2>${t("pz_parent_lang")}</h2>
        ${langRow("parentLang", state.settings.parentLocale || "kk")}
      </div>
    </section>
  </section>`;

  $("#back").onclick = () => navigate("today");
  $("#toStudio").onclick = () => navigate("studio", { unlocked: true });
  $("#toMicHelp").onclick = () => openMicHelp();
  $("#addKid").onclick = () => navigate("children", { add: true });
  view.querySelectorAll(".kid[data-id]").forEach(b => b.onclick = () => { setActiveChild(b.dataset.id); renderZone(); });
  $("#mv").onchange = async e => { await setModelVoice(e.target.checked); };
  if ($("#logout")) $("#logout").onclick = async () => {
    const note = $("#logoutNote");
    if (note.hidden){ note.hidden = false; $("#logout").textContent = t("pz_logout_confirm"); return; }
    await signOut(); navigate("onboarding");
  };
  if ($("#codeBand")) wireCode();
  if (opts.showCode && $("#codeBand")) $("#codeBand").scrollIntoView({ block: "center" });

  const bind = (id, key) => $("#" + id).querySelectorAll("[data-lang]").forEach(b => b.onclick = async () => {
    const l = b.dataset.lang;
    await setSetting(key, l);
    if (key === "childLocale") setLocale(l);
    $("#st").textContent = t("pz_saved");
    renderZone();
  });
  bind("childLang", "childLocale");
  bind("parentLang", "parentLocale");

  if (hasSession() && isOnline()) syncMe();
}

/* ---------- код семьи ---------- */
let familyCode = "";
function inviteLink(code){ return location.origin + "/?join=" + encodeURIComponent(code); }

async function wireCode(){
  const box = $("#famCode"), st = $("#codeSt");
  const show = code => { familyCode = code; if (box) box.textContent = code; };
  if (familyCode) show(familyCode);
  if (!isOnline()){ st.textContent = t("err_network"); return; }
  try { show((await api.familyCode()).code); } catch { st.textContent = t("err_network"); }

  $("#copyCode").onclick = async () => {
    if (!familyCode) return;
    try { await navigator.clipboard.writeText(familyCode); st.textContent = t("pz_code_copied"); }
    catch { st.textContent = familyCode; }
  };
  $("#shareCode").onclick = async () => {
    if (!familyCode) return;
    const url = inviteLink(familyCode);
    if (navigator.share){
      try { await navigator.share({ title: t("app_title"), text: t("pz_code_share_text", { code: familyCode }), url }); return; } catch { return; }
    }
    try { await navigator.clipboard.writeText(url); st.textContent = t("pz_code_link_copied"); } catch { st.textContent = url; }
  };
  $("#newCode").onclick = async () => {
    const btn = $("#newCode");
    if (!btn.dataset.sure){ btn.dataset.sure = "1"; btn.textContent = t("pz_code_new_confirm"); st.textContent = t("pz_code_new_warn"); return; }
    try { show((await api.newFamilyCode()).code); st.textContent = t("pz_code_new_done"); }
    catch { st.textContent = t("err_network"); }
    delete btn.dataset.sure; btn.textContent = t("pz_code_new");
  };
  $("#joinOther").onclick = () => navigate("onboarding", { step: "join" });
}
