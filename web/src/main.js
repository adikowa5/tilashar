/* Роутер представлений и старт приложения. */

import { hasSession, flushQueue, isOnline } from "./api.js";
import { state, loadCache, subscribe, syncMe, syncTopics, syncProgress, activeChild } from "./state.js";
import { t, onLocale, getLocale } from "./i18n.js";
import { stopAudio } from "./audio.js";
import { abortListening } from "./speech.js";
import { Rec } from "./recorder.js";
import { initVoices } from "./voices.js";

import * as onboarding from "./views/onboarding.js";
import * as children from "./views/children.js";
import * as today from "./views/today.js";
import * as lesson from "./views/lesson.js";
import * as results from "./views/results.js";
import * as studio from "./views/studio.js";
import * as parent from "./views/parent.js";

const VIEWS = { onboarding, children, today, lesson, results, studio, parent };

let gen = 0;
let current = { name: null, params: {} };

export function viewEl(){ return document.getElementById("view"); }
export function currentGen(){ return gen; }
export function currentView(){ return current.name; }
/* Каждая навигация двигает счётчик: зависшие async-цепочки видят, что они устарели, и выходят. */
export function bump(){ return ++gen; }

export function navigate(name, params = {}, opts = {}){
  const view = VIEWS[name];
  if (!view) return;
  bump();
  stopAudio();
  abortListening();
  if (Rec.open) Rec.close();
  if (current.name && VIEWS[current.name] && typeof VIEWS[current.name].leave === "function"){
    try { VIEWS[current.name].leave(); } catch {}
  }
  current = { name, params: params || {} };
  view.render(current.params);
  if (opts.scroll !== false) scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

/* Куда идти после входа: один ребёнок — сразу в день, иначе — выбор ребёнка. */
export function goAfterAuth(){
  if (!hasSession()) return navigate("onboarding");
  if (!state.children.length) return navigate("onboarding", { step: "child" });
  if (!activeChild()) return navigate("children");
  return navigate("today");
}

/* ---------- подвал и метатексты ---------- */
function paintChrome(){
  const f = document.getElementById("foot");
  if (f) f.innerHTML = `<span>${t("foot_model")}</span><span>${t("foot_mic")}</span>`;
  document.title = t("app_title");
  const d = document.querySelector('meta[name="description"]');
  if (d) d.setAttribute("content", t("app_desc"));
  document.documentElement.lang = getLocale();
}

/* ---------- сервис-воркер ---------- */
function registerSW(){
  if (!("serviceWorker" in navigator)) return;
  addEventListener("load", () => { navigator.serviceWorker.register("./sw.js").catch(() => {}); });
}

/* ---------- старт ---------- */
async function boot(){
  loadCache();
  paintChrome();
  onLocale(paintChrome);
  registerSW();
  initVoices();

  if (hasSession()){
    if (isOnline()){
      await syncMe();
      flushQueue();
      syncTopics().then(syncProgress);
    }
    goAfterAuth();
  } else {
    navigate("onboarding");
  }
  state.ready = true;
}

subscribe(() => {
  // язык интерфейса мог измениться вместе с активным ребёнком
  paintChrome();
});

boot();
