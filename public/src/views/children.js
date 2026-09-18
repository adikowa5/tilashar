/* Выбор ребёнка (аватары) и добавление ребёнка. */

import { navigate, viewEl } from "../main.js";
import { state, setActiveChild, syncMe, syncProgress, syncToday } from "../state.js";
import { api, hasSession, isOnline, ApiError } from "../api.js";
import { t } from "../i18n.js";
import { ICON, $, esc, avatarHTML } from "../ui.js";
import { childForm, wireChildForm } from "./onboarding.js";

let adding = false;

export function render(params){
  if (params && params.add) adding = true;
  paint();
  if (hasSession() && isOnline()) syncMe().then(ok => { if (ok) paint(); });
}

function paint(){
  const view = viewEl();
  const kids = state.children || [];
  view.innerHTML = `
  <section class="home">
    <div class="lesson-bar">
      <button class="btn ghost small" id="back" type="button">${ICON.back}${t("back")}</button>
      <span></span>
      <button class="btn ghost small" id="parentBtn" type="button">${ICON.gear}${t("pz_eyebrow")}</button>
    </div>
    <div class="section-head">
      <div>
        <p class="eyebrow">${t("ch_eyebrow")}</p>
        <h2>${t("ch_head")}</h2>
      </div>
    </div>
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
    ${adding ? `<div class="gate patch">
      <p class="eyebrow">${t("ch_add_head")}</p>
      ${childForm({ submit: t("ch_save"), cancel: true })}
    </div>` : ""}
  </section>`;

  $("#back").onclick = () => navigate("today");
  $("#parentBtn").onclick = () => navigate("parent");
  view.querySelectorAll(".kid[data-id]").forEach(b => b.onclick = () => {
    setActiveChild(b.dataset.id);
    syncProgress(); syncToday();
    navigate("today");
  });
  $("#addKid").onclick = () => { adding = true; paint(); };

  if (adding) wireChildForm(async child => {
    let created = null;
    try { created = await api.addChild(child); }
    catch (err){
      if (err instanceof ApiError && err.status === 0) created = null;
      else throw err;
    }
    if (created){
      state.children = [...state.children, created];
      setActiveChild(created.id);
    }
    adding = false;
    navigate("today");
  }, () => { adding = false; paint(); });
}

export function leave(){ adding = false; }
