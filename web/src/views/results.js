/* Итоги урока — перенесено из прототипа.
   Новое: гостю после первых «үш жұлдыз» предлагаем сохранить прогресс (POST /auth/claim). */

import { navigate, viewEl, currentGen } from "../main.js";
import { state, syncMe, syncProgress, syncToday } from "../state.js";
import { api, hasSession, ApiError, isOnline } from "../api.js";
import { t } from "../i18n.js";
import { ICON, $, esc, picHTML, tintOf, starsRow, confetti, sampleP } from "../ui.js";
import { play } from "../audio.js";
import { askTeacher } from "../ai.js";
import { flush } from "./lesson.js";

let R = null;

export function render(params){
  if (params && params.L) R = params.L;
  if (!R) return navigate("today");
  flush();
  const g = currentGen();
  const view = viewEl();
  const { topic, words, results } = R;
  const got = results.reduce((a, v) => a + (typeof v === "number" ? v : 0), 0);
  const checked = results.some(v => typeof v === "number");
  const offerSave = !!R.gotThree && (state.guest || !hasSession());

  view.innerHTML = `
  <section class="lesson" data-step="3">
    <div class="lesson-bar">
      <button class="btn ghost small" id="home" type="button">${ICON.back}${t("back_home")}</button>
      <span></span>
      <span class="count">${esc(topic.title)}</span>
    </div>
    <div class="stage patch">
      <p class="eyebrow">${t("res_eyebrow")}</p>
      <h2>${t("res_head")}</h2>
      ${checked ? `<div class="res-total" aria-label="${esc(t("res_total_aria", { got, total: words.length * 3 }))}">${ICON.star}${got} / ${words.length * 3}</div>` : ""}
      <ul class="res-list">
        ${words.map((w, k) => {
          const v = results[k];
          return `<li><span class="plate" style="--tint:${tintOf(topic)}">${picHTML(w)}</span>
            <span><b lang="kk">${esc(w[0])}</b>${v === "said" ? `<span class="mini"><span class="said">${t("res_said")}</span></span>` : starsRow(typeof v === "number" ? v : 0, "mini")}</span></li>`;
        }).join("")}
      </ul>
      ${offerSave ? `<aside class="teacher" id="claimBox">
        <p class="eyebrow">${t("parent_eyebrow")}</p>
        <p class="praise">${t("res_save_head")}</p>
        <p>${t("res_save_note")}</p>
        <form class="ai-form" id="claimForm">
          <div class="ai-row">
            <label class="sr" for="claimPhone">${t("ob_phone_label")}</label>
            <input id="claimPhone" inputmode="tel" autocomplete="tel" placeholder="${t("ob_phone_ph")}">
            <button class="btn plum" id="claimGo" type="submit">${t("ob_send_code")}</button>
          </div>
          <div class="ai-row" id="claimCodeRow" hidden>
            <label class="sr" for="claimCode">${t("ob_code_label")}</label>
            <input id="claimCode" inputmode="numeric" maxlength="6" placeholder="${t("ob_code_ph")}">
            <button class="btn plum" id="claimConfirm" type="button">${t("res_save_btn")}</button>
          </div>
          <p class="status" id="claimStatus"></p>
        </form>
      </aside>` : ""}
      <aside class="teacher" id="teacher" hidden>
        <p class="eyebrow">${t("teacher_eyebrow")}</p>
        <p class="praise wait" id="tPraise">${t("teacher_wait")}</p>
        <p id="tTip" hidden></p>
        <div class="actions" id="tPractice" style="justify-content:flex-start;min-height:0"></div>
      </aside>
      <div class="actions">
        <button class="btn" id="again" type="button">${ICON.repeat}${t("res_again")}</button>
        <button class="btn primary" id="homeBtn" type="button">${t("res_other_topic")}${ICON.arrow}</button>
      </div>
    </div>
  </section>`;

  $("#home").onclick = () => navigate("today");
  $("#homeBtn").onclick = () => navigate("today");
  $("#again").onclick = () => navigate("lesson", { topic, words });
  play("p:done");
  if (got === words.length * 3 && checked) setTimeout(() => { if (currentGen() === g) confetti($(".res-total")); }, 300);
  if (offerSave) wireClaim();
  if (checked) sampleP.then(sample => {
    if (sample && currentGen() === g) askTeacher(sample, R, practice => navigate("lesson", { topic, words: practice }));
  });
  syncProgress(); syncToday();
}

/* ---------- «сохранить прогресс»: телефон → код → claim ---------- */
function wireClaim(){
  const form = $("#claimForm"), phone = $("#claimPhone"), code = $("#claimCode");
  const row = $("#claimCodeRow"), statusEl = $("#claimStatus"), go = $("#claimGo"), confirm = $("#claimConfirm");
  const fail = err => {
    const map = {
      phone_invalid: "err_phone_invalid", code_invalid: "err_code_invalid", code_expired: "err_code_expired",
      code_not_found: "err_code_not_found", too_many_attempts: "err_too_many", already_claimed: "err_already_claimed",
      offline: "err_network"
    };
    statusEl.textContent = t(map[err && err.code] || "err_save");
  };
  form.onsubmit = async e => {
    e.preventDefault();
    const num = phone.value.trim();
    if (!/^\+?\d{10,15}$/.test(num.replace(/[\s()-]/g, ""))) return fail(new ApiError("phone_invalid"));
    go.disabled = true; statusEl.textContent = "";
    try {
      const out = await api.sendCode(num.replace(/[\s()-]/g, ""));
      row.hidden = false; code.focus();
      if (out && out.dev_code) statusEl.textContent = t("ob_dev_code", { code: out.dev_code });
    } catch (err){ fail(err); }
    go.disabled = false;
  };
  confirm.onclick = async () => {
    confirm.disabled = true; statusEl.textContent = "";
    try {
      await api.claim(phone.value.trim().replace(/[\s()-]/g, ""), code.value.trim());
      await syncMe();
      statusEl.textContent = t("pz_saved");
      $("#claimBox").hidden = true;
      if (isOnline()) syncProgress();
    } catch (err){ fail(err); }
    confirm.disabled = false;
  };
}

