/* Помощь с микрофоном для родителя: проверка в один клик и пошаговые инструкции
   для iPhone, Android и компьютера. Открывается из урока, из подвала и из родительского раздела. */

import { navigate, viewEl, currentGen } from "../main.js";
import { t, onLocale } from "../i18n.js";
import { ICON, $ } from "../ui.js";
import { playWav, stopAudio } from "../audio.js";
import { recordOnce, stopOnce } from "../recorder.js";
import { micEnv } from "../speech.js";

const STEPS = {
  ios: ["mh_ios_1", "mh_ios_2", "mh_ios_3", "mh_ios_4", "mh_ios_5", "mh_ios_6"],
  android: ["mh_android_1", "mh_android_2", "mh_android_3", "mh_android_4", "mh_android_5"],
  desktop: ["mh_desktop_1", "mh_desktop_2", "mh_desktop_3"]
};
const NOTE = { ios: "mh_ios_note", desktop: "mh_desktop_note" };

let from = "today", fromParams = {}, tab = null, testing = false, offLocale = null;

export function render(params = {}){
  if (params.from){ from = params.from; fromParams = params.fromParams || {}; }
  tab = tab || micEnv().platform;
  if (!offLocale) offLocale = onLocale(() => { if (viewEl().querySelector(".mic-help")) paint(); });
  paint();
}

export function leave(){ stopOnce(); testing = false; }

function paint(){
  const env = micEnv();
  const tabs = ["ios", "android", "desktop"];
  viewEl().innerHTML = `
  <section class="mic-help">
    <div class="lesson-bar">
      <button class="btn ghost small" id="back" type="button">${ICON.back}${t("back")}</button>
      <span></span>
      <span class="count">${t("mh_eyebrow")}</span>
    </div>

    <div class="studio-head patch">
      <div>
        <p class="eyebrow">${t("mh_eyebrow")}</p>
        <h2>${t("mh_head")}</h2>
        <p class="note">${t("mh_lead")}</p>
        ${env.inapp ? `<p class="tip">${t("l_inapp")}</p>` : ""}
      </div>
      <div class="studio-ctrl">
        <h3 class="mh-sub">${t("mh_test_head")}</h3>
        <p class="note">${t("mh_test_note")}</p>
        <button class="btn red" id="test" type="button">${ICON.mic}${t("mh_test_btn")}</button>
        <div class="level" aria-hidden="true"><i id="lvl"></i></div>
        <p class="status" id="testStatus" role="status"></p>
        <p class="note">${t(env.canRecognize ? "mh_speech_yes" : "mh_speech_no")}</p>
      </div>
    </div>

    <div class="tabs" role="tablist">
      ${tabs.map(k => `<button class="chip" type="button" role="tab" data-tab="${k}" aria-selected="${k === tab}" aria-pressed="${k === tab}">${t("mh_tab_" + k)}${k === env.platform ? `<small>${t("mh_yours")}</small>` : ""}</button>`).join("")}
    </div>

    <section class="patch mh-steps" role="tabpanel">
      <ol>${STEPS[tab].map(k => `<li>${t(k)}</li>`).join("")}</ol>
      ${NOTE[tab] ? `<p class="tip">${t(NOTE[tab])}</p>` : ""}
    </section>
  </section>`;

  $("#back").onclick = () => navigate(from, fromParams);
  viewEl().querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { tab = b.dataset.tab; paint(); });
  $("#test").onclick = runTest;
}

async function runTest(){
  const btn = $("#test"), st = $("#testStatus"), lvl = $("#lvl");
  if (testing){ stopOnce(); return; }
  const env = micEnv();
  if (!env.canRecord){ st.textContent = t("mh_test_none"); return; }
  const g = currentGen();
  stopAudio();
  testing = true;
  btn.innerHTML = ICON.stop + t("mh_test_rec");
  st.textContent = t("mh_test_rec");
  try {
    const rec = await recordOnce({ onLevel: rms => { if (lvl) lvl.style.width = Math.min(100, Math.round(Math.sqrt(rms) * 260)) + "%"; } });
    if (g !== currentGen()) return;
    st.textContent = t("mh_test_ok");
    await playWav(rec.wav);
  } catch (e){
    if (g !== currentGen()) return;
    const name = e && e.name, code = e && e.code;
    st.textContent = code === "quiet" ? t("mh_test_quiet")
      : (name === "NotAllowedError" || name === "SecurityError") ? t("mh_test_denied")
      : (name === "NotFoundError" || name === "NotReadableError" || name === "OverconstrainedError") ? t("mh_test_missing")
      : t("mh_test_none");
  } finally {
    testing = false;
    if (g === currentGen()){
      const b = $("#test"); if (b) b.innerHTML = ICON.mic + t("mh_test_btn");
      const l = $("#lvl"); if (l) l.style.width = "0";
    }
  }
}
