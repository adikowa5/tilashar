/* Родительская зона: список детей, язык интерфейса ребёнка и родителя,
   переключатель модельного голоса. Вход — через «взрослую дверь»: задача на умножение. */

import { navigate, viewEl } from "../main.js";
import { state, setSetting, setActiveChild, signOut, syncMe } from "../state.js";
import { hasSession, isOnline } from "../api.js";
import { t, setLocale } from "../i18n.js";
import { ICON, $, esc, avatarHTML } from "../ui.js";
import { modelVoiceOn, setModelVoice } from "../voices.js";

let unlocked = false;
let gate = null;

export function leave(){ unlocked = false; gate = null; }

function newGate(){
  const a = 3 + Math.floor(Math.random() * 7);   // 3..9
  const b = 3 + Math.floor(Math.random() * 7);
  return { a, b, answer: a * b };
}

export function render(){
  if (!unlocked){ gate = gate || newGate(); return renderGate(); }
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
    if (+$("#ans").value.trim() === gate.answer){ unlocked = true; renderZone(); }
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
        ${state.guest ? `<p class="note">${t("pz_guest_note")}</p>` : ""}
      </div>
      <div class="studio-ctrl">
        <label class="switch" for="mv"><input type="checkbox" id="mv" ${modelVoiceOn() ? "checked" : ""}><span>${t("pz_model_voice")}</span></label>
        <button class="btn red" id="toStudio" type="button">${ICON.mic}${t("pz_voice_studio")}</button>
        ${hasSession() ? `<button class="btn ghost" id="logout" type="button">${t("pz_logout")}</button>` : ""}
        <p class="status" id="st"></p>
      </div>
    </div>

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
  $("#toStudio").onclick = () => navigate("studio");
  $("#addKid").onclick = () => navigate("children", { add: true });
  view.querySelectorAll(".kid[data-id]").forEach(b => b.onclick = () => { setActiveChild(b.dataset.id); renderZone(); });
  $("#mv").onchange = async e => { await setModelVoice(e.target.checked); };
  if ($("#logout")) $("#logout").onclick = async () => { await signOut(); navigate("onboarding"); };

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
