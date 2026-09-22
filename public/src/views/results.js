/* Итоги урока.
   После первых «үш жұлдыз» один раз подсказываем родителю про код семьи:
   с ним прогресс не пропадёт при смене телефона. */

import { navigate, viewEl, currentGen } from "../main.js";
import { syncProgress, syncToday } from "../state.js";
import { hasSession, store } from "../api.js";
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
  const offerSave = !!R.gotThree && hasSession() && !store.get("codeHintShown", false);

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
      ${offerSave ? `<aside class="teacher" id="codeHint">
        <p class="eyebrow">${t("parent_eyebrow")}</p>
        <p class="praise">${t("res_code_head")}</p>
        <p>${t("res_code_note")}</p>
        <div class="actions" style="justify-content:flex-start;min-height:0">
          <button class="btn plum" id="toCode" type="button">${t("res_code_btn")}${ICON.arrow}</button>
        </div>
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
  if (offerSave){
    store.set("codeHintShown", true);
    $("#toCode").onclick = () => navigate("parent", { showCode: true });
  }
  if (checked) sampleP.then(sample => {
    if (sample && currentGen() === g) askTeacher(sample, R, practice => navigate("lesson", { topic, words: practice }));
  });
  syncProgress(); syncToday();
}
