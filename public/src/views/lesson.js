/* Урок: шаги Тыңда / Қайтала / Айт — перенесено из прототипа.
   Новое: результат каждой попытки уходит в API (POST /children/{id}/attempts),
   а в офлайне — в очередь досылки. */

import { navigate, viewEl, currentGen, bump, openMicHelp } from "../main.js";
import { state, activeChild, recordStars, syncToday } from "../state.js";
import { api, hasSession } from "../api.js";
import { t } from "../i18n.js";
import { ICON, $, esc, sleep, picHTML, tintOf, wordHTML, sylls, starsRow, confetti } from "../ui.js";
import { play, playWav, stopAudio } from "../audio.js";
import { recordOnce, stopOnce } from "../recorder.js";
import { SR, listen, score, tipFor, activeRec, abortListening, micEnv } from "../speech.js";

export let L = null;
/* Как проходит шаг «Айт»:
   asr     — браузер распознаёт казахский и ставит звёзды (Chrome на Android и компьютере);
   self    — распознавания нет (iPhone, Safari, Firefox): ребёнок пишет себя и слушает;
   blocked — микрофон запрещён или не найден: показываем, как включить;
   manual  — микрофона нет совсем: родитель слушает и жмёт «Айттым!». */
const ENV = micEnv();
const initialMode = () => ENV.canRecognize ? "asr" : ENV.canRecord ? "self" : "manual";
let micMode = initialMode();
let listening = false;
let pending = [];              // попытки, ещё не ушедшие на сервер

export function lessonState(){ return L; }

export function render(params){
  if (params && params.topic){
    L = {
      topic: params.topic,
      words: params.words || params.topic.words,
      i: 0, step: 1, results: [], introPlayed: false,
      dayMode: !!params.dayMode
    };
    pending = [];
    if (micMode !== "manual") micMode = initialMode();
  }
  if (!L) return navigate("today");
  paint();
}

function paint(){
  bump(); stopAudio(); abortListening(); stopOnce(); listening = false;
  const view = viewEl();
  const { topic, words, i, step } = L, w = words[i];
  const labels = [t("step_listen"), t("step_repeat"), t("step_say")];
  const icons = [ICON.ear, ICON.repeat, ICON.mic];
  const pct = Math.round(((i + (step - 1) / 3) / words.length) * 100);
  view.innerHTML = `
  <section class="lesson" data-step="${step}">
    <div class="lesson-bar">
      <button class="btn ghost small" id="home" type="button">${ICON.back}${t("back_home")}</button>
      <ol class="steps" aria-label="${t("lesson_steps")}">
        ${labels.map((l, k) => `<li class="${k + 1 === step ? "on" : k + 1 < step ? "done" : ""}"${k + 1 === step ? ' aria-current="step"' : ""}><span class="ic">${k + 1 < step ? ICON.check : icons[k]}</span><span class="lbl">${l}</span></li>`).join("")}
      </ol>
      <span class="count" aria-label="${esc(t("lesson_count_aria", { i: i + 1, n: words.length }))}">${i + 1} / ${words.length}</span>
    </div>
    <div class="thread" aria-hidden="true"><i style="width:${pct}%"></i></div>
    <div class="stage patch">
      <div class="plate" style="--tint:${tintOf(topic)}">${picHTML(w)}</div>
      <div class="word${step === 2 ? " split" : ""}" id="word" lang="kk">${wordHTML(w)}</div>
      <p class="say" id="say"></p>
      <div id="zone"></div>
      <p class="heard" id="heard"></p>
      <p class="tip" id="tip" hidden></p>
      <div class="actions" id="actions"></div>
    </div>
  </section>`;
  $("#home").onclick = () => { flush(); navigate("today"); };
  if (step === 1) stepListen(w);
  else if (step === 2) stepRepeat(w);
  else stepSay(w);
}

/* перерисовка шага без прохода через роутер — счётчик gen двигаем сами */
function repaint(){ paint(); }

const say = txt => { const el = $("#say"); if (el) el.textContent = txt; };
const heard = txt => { const el = $("#heard"); if (el) el.textContent = txt; };
const tip = txt => { const el = $("#tip"); if (!el) return; el.textContent = txt || ""; el.hidden = !txt; };

function actions(list){
  const box = $("#actions"); if (!box) return;
  box.innerHTML = "";
  list.forEach(([cls, html, fn]) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "btn " + cls; b.innerHTML = html; b.onclick = fn;
    box.appendChild(b);
  });
}

function speakWord(w, opts = {}){
  const syl = [...document.querySelectorAll("#word .syl")];
  const parts = sylls(w), lens = parts.map(p => [...p].length), total = lens.reduce((a, b) => a + b, 0);
  const light = p => {
    let acc = 0, idx = -1;
    for (let k = 0; k < lens.length; k++){ acc += lens[k] / total; if (p < acc * 0.98){ idx = k; break; } }
    if (p >= 1) idx = -1;
    syl.forEach((s, k) => s.classList.toggle("lit", k === idx || (p > 0.02 && p < 1 && idx === -1 && k === lens.length - 1)));
  };
  return play("w:" + w[0], { ...opts, onProgress: light });
}

function go(step){ L.step = step; repaint(); }
function nextWord(){
  L.i++; L.step = 1;
  flush();
  if (L.i >= L.words.length) navigate("results", { L });
  else { repaint(); scrollTo({ top: 0, behavior: "smooth" }); }
}

async function stepListen(w){
  const g = currentGen();
  say(t("l_listen_say"));
  actions([
    ["", ICON.speaker + t("l_listen_again"), () => speakWord(w)],
    ["primary", t("l_to_repeat") + ICON.arrow, () => go(2)]
  ]);
  await sleep(350); if (g !== currentGen()) return;
  speakWord(w);
}

async function stepRepeat(w){
  const g = currentGen();
  const zone = $("#zone");
  actions([]); zone.innerHTML = "";
  say(t("l_repeat_say"));
  await sleep(300); if (g !== currentGen()) return;
  await speakWord(w); if (g !== currentGen()) return;
  await sleep(700); if (g !== currentGen()) return;
  await speakWord(w); if (g !== currentGen()) return;
  await play("p:your_turn"); if (g !== currentGen()) return;
  say(t("l_your_turn"));
  const ms = 2800;
  zone.innerHTML = `<div class="turn" role="presentation"><i style="--dur:${ms}ms;animation-duration:${ms}ms"></i></div>`;
  await sleep(ms); if (g !== currentGen()) return;
  zone.innerHTML = "";
  say(t("l_repeat_done"));
  actions([
    ["", ICON.repeat + t("l_once_more"), () => stepRepeat(w)],
    ["primary", t("l_to_mic") + ICON.arrow, () => go(3)]
  ]);
}

/* ---------- запись результата ---------- */
function recordResult(val, heardText, mode){
  const prev = L.results[L.i];
  if (val === "said"){ if (prev === undefined) L.results[L.i] = "said"; }
  else L.results[L.i] = typeof prev === "number" ? Math.max(prev, val) : val;

  const w = L.words[L.i];
  const stars = typeof val === "number" ? val : 0;
  recordStars(w, stars);
  if (w.id){
    pending.push({
      word_id: w.id,
      stars,
      heard: heardText || null,
      mode: mode || (val === "said" ? "manual" : "asr"),
      at: new Date().toISOString()
    });
  }
  if (pending.length >= 8) flush();
}

/* Отправка попыток. Офлайн и гость без сессии — api.attempts сам положит в очередь. */
export function flush(){
  if (!pending.length) return;
  const child = activeChild();
  const list = pending; pending = [];
  if (!child) return;                     // некому засчитывать — остаётся только локальный кеш
  api.attempts(child.id, list).then(out => {
    if (out && typeof out === "object"){
      const c = activeChild();
      if (c){
        if (typeof out.stars_total === "number") c.stars_total = out.stars_total;
        if (typeof out.streak === "number") c.streak = out.streak;
      }
      syncToday();
    }
  }).catch(() => {});
}

const isLast = () => L.i >= L.words.length - 1;
const nextBtn = () => ["primary", (isLast() ? t("l_results") : t("l_next_word")) + ICON.arrow, nextWord];

function stepSay(w){
  if (micMode === "manual") return manualSay(w, null);
  if (micMode === "blocked") return blockedSay(w, L.micError);
  if (micMode === "self") return stepSelf(w);
  const zone = $("#zone");
  say(t("l_mic_say"));
  zone.innerHTML = `<div class="mic-zone">
      <button class="mic" id="mic" type="button" aria-label="${t("l_mic_aria")}">${ICON.mic}</button>
      <p class="mic-label" id="micLabel">${t("l_mic_label")}</p>
      ${starsRow(0)}
    </div>`;
  actions([["", ICON.speaker + t("l_play_model"), () => speakWord(w)]]);
  if (ENV.inapp) tip(t("l_inapp"));
  $("#mic").onclick = () => onMic(w);
  if (!L.introPlayed){ L.introPlayed = true; play("p:mic_intro"); }
}

async function onMic(w){
  const g = currentGen();
  const mic = $("#mic"), label = $("#micLabel");
  if (listening){ try { activeRec && activeRec.stop(); } catch {} return; }
  stopAudio();
  listening = true; mic.classList.add("live"); label.textContent = t("l_listening");
  say(t("l_say_now")); heard(""); tip("");
  $(".mic-zone .stars").outerHTML = starsRow(0);
  const r = await listen(txt => { if (g === currentGen()) heard("«" + txt + "»"); });
  listening = false;
  if (g !== currentGen()) return;
  mic.classList.remove("live"); label.textContent = t("l_press_again");

  // Нет доступа к микрофону — объясняем, как включить. Не работает само распознавание —
  // переходим на «запиши и послушай себя», урок не останавливается.
  if (r.error === "not-allowed" || r.error === "audio-capture"){
    micMode = "blocked"; L.micError = r.error === "audio-capture" ? "NotFoundError" : "NotAllowedError";
    return blockedSay(w, L.micError);
  }
  const speechErrors = ["service-not-allowed", "unsupported", "language-not-supported", "network", "start"];
  if (r.error && speechErrors.includes(r.error)){
    micMode = ENV.canRecord ? "self" : "manual";
    return micMode === "self" ? stepSelf(w) : manualSay(w, r.error);
  }

  const alts = (r.alts || []).filter(a => a && a.trim());
  if (!alts.length){
    say(t("l_not_heard"));
    play("p:silent");
    actions([["", ICON.speaker + t("l_play_model"), () => speakWord(w)], nextBtn()]);
    return;
  }
  const res = score(w[0], alts);
  heard(t("l_heard", { text: res.heard }));
  $(".mic-zone .stars").outerHTML = starsRow(res.stars);
  const msg = { 3: [t("l_great"), "great"], 2: [t("l_good"), "good"], 1: [t("l_almost"), "almost"], 0: [t("l_again"), "again"] }[res.stars];
  say(msg[0]);
  play("p:" + msg[1]);
  const tipKey = res.stars < 3 ? tipFor(w[0], res.tok) : null;
  tip(tipKey ? t(tipKey) : "");
  recordResult(res.stars, res.heard, "asr");
  if (res.stars === 3){ confetti(mic); markThreeStars(); }
  actions([["", ICON.speaker + t("l_play_model"), () => speakWord(w)], nextBtn()]);
}

/* Первые «үш жұлдыз» у гостя — повод предложить сохранить прогресс (см. results.js). */
function markThreeStars(){
  if (state.guest || !hasSession()) L.gotThree = true;
}

/* ---------- «запиши и послушай себя» ---------- */
function stepSelf(w){
  const zone = $("#zone");
  say(t("l_self_say"));
  zone.innerHTML = `<div class="mic-zone">
      <button class="mic" id="mic" type="button" aria-label="${t("l_mic_aria")}">${ICON.mic}</button>
      <p class="mic-label" id="micLabel">${t("l_mic_label")}</p>
    </div>`;
  heard(!L.selfNoted ? t(ENV.ios ? "l_self_note_ios" : "l_self_note") : "");
  L.selfNoted = true;
  if (ENV.inapp) tip(t("l_inapp"));
  actions([["", ICON.speaker + t("l_play_model"), () => speakWord(w)]]);
  $("#mic").onclick = () => onSelfMic(w);
  if (!L.introPlayed){ L.introPlayed = true; play("p:mic_intro"); }
}

async function onSelfMic(w){
  const g = currentGen();
  const mic = $("#mic"), label = $("#micLabel");
  if (listening){ stopOnce(); return; }
  stopAudio();
  listening = true;
  mic.classList.add("live"); label.textContent = t("l_listening");
  say(t("l_say_now")); heard(""); tip("");
  let rec;
  try {
    rec = await recordOnce({ onLevel: rms => mic.style.setProperty("--lvl", Math.min(1, Math.sqrt(rms) * 2.6).toFixed(2)) });
  } catch (e){
    listening = false;
    if (g !== currentGen()) return;
    mic.classList.remove("live"); mic.style.removeProperty("--lvl"); label.textContent = t("l_mic_label");
    if (e && e.code === "quiet"){ say(t("l_not_heard")); play("p:silent"); return; }
    if (e && e.name === "NotSupportedError"){ micMode = "manual"; return manualSay(w, "unsupported"); }
    micMode = "blocked"; L.micError = e && e.name;
    return blockedSay(w, L.micError);
  }
  listening = false;
  if (g !== currentGen()) return;
  mic.classList.remove("live"); mic.style.removeProperty("--lvl"); label.textContent = t("l_press_again");

  const takeId = "take@" + L.i + "@" + Date.now();
  const again = () => playWav(rec.wav, takeId);
  say(t("l_self_listen"));
  await again(); if (g !== currentGen()) return;
  await sleep(450); if (g !== currentGen()) return;
  say(t("l_self_compare"));
  await speakWord(w); if (g !== currentGen()) return;
  say(t("l_self_ask"));
  actions([
    ["", ICON.play + t("l_play_me"), again],
    ["", ICON.speaker + t("l_play_model"), () => speakWord(w)],
    ["primary", ICON.check + t("l_said_it"), () => {
      recordResult("said", null, "manual");
      say(t("l_good")); play("p:good");
      confetti($("#mic"));
      actions([["", ICON.play + t("l_play_me"), again], nextBtn()]);
    }]
  ]);
}

/* ---------- микрофон запрещён или не найден ---------- */
function blockedSay(w, errName){
  const zone = $("#zone");
  zone.innerHTML = "";
  say(t("l_manual_say"));
  const missing = errName === "NotFoundError" || errName === "NotReadableError" || errName === "OverconstrainedError";
  heard(t(missing ? "l_mic_missing" : "l_mic_blocked"));
  tip(ENV.inapp ? t("l_inapp") : "");
  actions([
    ["primary", ICON.mic + t("l_mic_help"), () => openMicHelp()],
    ["", ICON.repeat + t("l_try_again"), () => { micMode = initialMode(); L.micError = null; repaint(); }],
    ["", t("l_without_mic"), () => { micMode = "manual"; manualSay(w, "declined"); }]
  ]);
}

function manualSay(w, err){
  const zone = $("#zone");
  zone.innerHTML = "";
  say(t("l_manual_say"));
  heard(err === "unsupported" || !SR ? t("l_manual_unsupported") : t("l_manual_nomic"));
  actions([
    ["", ICON.speaker + t("l_play_model"), () => speakWord(w)],
    ["primary", ICON.check + t("l_said_it"), () => {
      recordResult("said", null, "manual");
      say(t("l_good")); play("p:good");
      actions([["", ICON.speaker + t("l_play_model"), () => speakWord(w)], nextBtn()]);
    }],
    ["", ICON.mic + t("l_mic_help"), () => openMicHelp()]
  ]);
}

export function leave(){ flush(); }
