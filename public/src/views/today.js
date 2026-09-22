/* Экран «Бүгін»: серия дней, прогресс дня, одна большая кнопка «Жалғастыр», список тем ниже. */

import { navigate, viewEl, currentGen } from "../main.js";
import { state, allTopics, topicById, topicScore, activeChild, syncToday, starsFor } from "../state.js";
import { t } from "../i18n.js";
import { ICON, $, esc, picHTML, topicPic, tintOf, avatarHTML, sampleP } from "../ui.js";
import { play } from "../audio.js";
import { voiceKeys, recordedCount, onVoices } from "../voices.js";
import { setupAI, aiStatus } from "../ai.js";

let unVoices = null;
let lastDay = "";          // подпись последнего отрисованного состава дня — чтобы не перерисовывать по кругу

export function leave(){ if (unVoices){ unVoices(); unVoices = null; } lastDay = ""; }

/* ---------- состав дня ---------- */
const todayKey = () => new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 10);

export function dayPlan(){
  const day = state.today;
  const topics = allTopics();
  if (day && Array.isArray(day.items) && day.items.length){
    const words = day.items.map(it => {
      const tp = topicById(it.topic_slug);
      const w = tp && tp.words.find(x => x.id === it.word_id);
      return w ? { w, topic: tp, status: it.status } : null;
    }).filter(Boolean);
    if (words.length) return { words, streak: day.streak || 0, done: day.done || 0, total: day.total || words.length, topic: words[0].topic };
  }
  // офлайн / без аккаунта: 8 слов с наименьшим числом звёзд
  const pool = [];
  topics.forEach(tp => tp.words.forEach(w => pool.push({ w, topic: tp, status: starsFor(w) >= 3 ? "done" : (starsFor(w) ? "review" : "new") })));
  pool.sort((a, b) => starsFor(a.w) - starsFor(b.w));
  const words = pool.slice(0, 8);
  const done = words.filter(x => starsFor(x.w) >= 3).length;
  const c = activeChild();
  return { words, streak: (c && c.streak) || 0, done, total: words.length, topic: words.length ? words[0].topic : topics[0] };
}

export function render(){
  const g = currentGen();
  const view = viewEl();
  const child = activeChild();
  const plan = dayPlan();
  const pool = allTopics().flatMap(tp => tp.words.map(w => ({ t: tp, w })));
  const dayNo = Math.floor((Date.now() + 5 * 3600e3) / 86400e3);
  const wotd = pool.length ? pool[dayNo % pool.length] : null;
  const pct = plan.total ? Math.round(plan.done / plan.total * 100) : 0;
  const allDone = plan.total > 0 && plan.done >= plan.total;

  view.innerHTML = `
  <section class="home">
    <div class="lesson-bar">
      <button class="btn ghost small" id="whoBtn" type="button">${child ? `<span class="kid-mini">${avatarHTML(child.avatar)}</span>` : ICON.user}${esc(child ? child.name : t("ch_head"))}</button>
      <span></span>
      <button class="btn ghost small" id="parentBtn" type="button">${ICON.gear}${t("pz_eyebrow")}</button>
    </div>

    <div class="hero">
      <div>
        <p class="eyebrow">${t("today_eyebrow")}</p>
        <h1>${child ? esc(t("today_hello", { name: child.name })) : t("app_title")}</h1>
        <p class="lede">${t("home_lede")}</p>
        <div class="day">
          <p class="streakline">${ICON.flame}<b>${plan.streak > 0 ? esc(t("today_streak", { n: plan.streak })) : t("today_streak_zero")}</b></p>
          <span class="meter" aria-label="${t("today_day_aria")}"><i style="width:${pct}%"></i></span>
          <p class="pb-count">${esc(t("today_progress", { done: plan.done, total: plan.total }))}</p>
          ${!state.online ? `<p class="note">${t("offline_note")}</p>` : ""}
        </div>
        <button class="btn primary big" id="go" type="button">${allDone ? t("today_start") : (plan.done ? t("today_continue") : t("today_start"))}${ICON.arrow}</button>
        ${allDone ? `<p class="note">${t("today_done_note")}</p>` : ""}
        <ol class="how" aria-label="${t("steps_label")}">
          <li><span class="dot s1">${ICON.ear}</span>${t("step_listen")}</li>
          <li class="arrow" aria-hidden="true">${ICON.arrow}</li>
          <li><span class="dot s2">${ICON.repeat}</span>${t("step_repeat")}</li>
          <li class="arrow" aria-hidden="true">${ICON.arrow}</li>
          <li><span class="dot s3">${ICON.mic}</span>${t("step_say")}</li>
        </ol>
      </div>
      ${wotd ? `<article class="wotd patch">
        <div class="plate" style="--tint:${tintOf(wotd.t)}">${picHTML(wotd.w)}</div>
        <div class="wotd-body">
          <p class="eyebrow">${t("wotd_eyebrow")}</p>
          <div class="wotd-word">${esc(wotd.w[0])}</div>
          <div class="wotd-row">
            <button class="btn small" id="wotdPlay" type="button">${ICON.speaker}${t("btn_listen")}</button>
            <button class="btn small primary" id="wotdGo" type="button">${esc(wotd.t.title)}${ICON.arrow}</button>
          </div>
        </div>
      </article>` : ""}
    </div>

    <div class="section-head">
      <h2>${t("topics_head")}</h2>
      <p>${t("topics_sub")}</p>
    </div>
    <div class="topics">
      ${allTopics().map(tp => {
        const { got, total } = topicScore(tp);
        return `<button class="tile" type="button" data-topic="${esc(tp.id)}" style="--tint:${tintOf(tp)}">
          <span class="tpic">${topicPic(tp)}</span>
          <span class="tinfo">
            ${tp.custom ? `<span class="badge">${t("badge_teacher")}</span>` : ""}
            <span class="tname">${esc(tp.title)}</span>
            <span class="meter"><i style="width:${total ? Math.round(got / total * 100) : 0}%"></i></span>
            <span class="meta"><span>${esc(t("n_words", { n: tp.words.length }))}</span><span class="got">${ICON.star}${got} / ${total}</span></span>
          </span>
        </button>`;
      }).join("")}
    </div>

    <section class="parent-band patch">
      <div>
        <p class="eyebrow">${t("parent_eyebrow")}</p>
        <h2>${t("parent_band_head")}</h2>
        <p class="note">${t("parent_band_note")}</p>
      </div>
      <div class="pb-side">
        <p class="pb-count"><b id="pbCount">0</b>/ <span id="pbTotal">0</span> ${t("recorded_suffix")}</p>
        <span class="meter"><i id="pbMeter" style="width:0%"></i></span>
        <button class="btn red" id="toStudio" type="button">${ICON.mic}${t("btn_record_voice")}</button>
      </div>
    </section>

    <section class="ai-band patch" id="aiBand" hidden>
      <div>
        <p class="eyebrow">${t("ai_eyebrow")}</p>
        <h2>${t("ai_head")}</h2>
        <p class="note">${t("ai_note")}</p>
      </div>
      <form class="ai-form" id="aiForm">
        <div class="ai-row">
          <label class="sr" for="aiTheme">${t("ai_label")}</label>
          <input id="aiTheme" name="aiTheme" maxlength="40" placeholder="${t("ai_placeholder")}" autocomplete="off">
          <button class="btn plum" id="aiGo" type="submit">${t("ai_submit")}</button>
        </div>
        <div class="chips">
          ${[1,2,3,4,5,6].map(i => `<button class="chip" type="button" data-chip="${esc(t("ai_chip_" + i))}">${esc(t("ai_chip_" + i))}</button>`).join("")}
        </div>
        <p class="status" id="aiStatus">${esc(aiStatus())}</p>
      </form>
    </section>
  </section>`;

  $("#whoBtn").onclick = () => navigate("children");
  $("#parentBtn").onclick = () => navigate("parent");
  $("#go").onclick = () => startDay(plan);
  $("#toStudio").onclick = () => navigate("parent", { next: "studio" });
  if (wotd){
    $("#wotdPlay").onclick = () => play("w:" + wotd.w[0]);
    $("#wotdGo").onclick = () => navigate("lesson", { topic: wotd.t, words: wotd.t.words });
  }
  view.querySelectorAll(".tile").forEach(b => b.onclick = () => {
    const tp = topicById(b.dataset.topic);
    if (tp) navigate("lesson", { topic: tp, words: tp.words });
  });

  updateParentBand();
  if (unVoices) unVoices();
  unVoices = onVoices(() => { if (currentGen() === g) updateParentBand(); });

  lastDay = JSON.stringify(state.today || null);

  sampleP.then(sample => { if (sample && currentGen() === g) setupAI(sample, () => render()); });
  syncToday().then(d => {
    if (currentGen() !== g) return;
    if (JSON.stringify(d || null) !== lastDay) render();     // перерисовываем только если день реально изменился
  });
}

function startDay(plan){
  if (!plan.words.length) return;
  const words = plan.words.map(x => x.w);
  const topic = plan.topic || allTopics()[0];
  navigate("lesson", { topic, words, dayMode: true });
}

export function updateParentBand(){
  const el = $("#pbCount"); if (!el) return;
  const keys = voiceKeys(), n = recordedCount(keys);
  el.textContent = n;
  $("#pbTotal").textContent = keys.length;
  $("#pbMeter").style.width = (keys.length ? Math.round(n / keys.length * 100) : 0) + "%";
}
