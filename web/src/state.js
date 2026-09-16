/* Состояние приложения: family, children, activeChild, progress, settings.
   Источник истины — API; localStorage используется только как кеш для офлайна. */

import { store, api, hasSession, isOnline, clearTokens } from "./api.js";
import { TOPICS as BUILTIN } from "./words.js";
import { setLocale } from "./i18n.js";

const listeners = new Set();

export const state = {
  user: null,
  family: null,
  children: [],
  activeChildId: null,
  topics: [],                 // нормализованные темы (встроенные + семейные)
  customTopics: [],           // темы, придуманные «ұстазом» и ещё не ушедшие на сервер
  progress: {},               // word_id -> {stars, attempts}
  bestStars: {},              // текст слова -> лучшие звёзды (для плиток тем)
  today: null,                // {date, streak, done, total, items}
  settings: { modelVoice: true, childLocale: "kk", parentLocale: "kk" },
  online: isOnline(),
  guest: false,
  ready: false
};

export function subscribe(fn){ listeners.add(fn); return () => listeners.delete(fn); }
export function emit(){ listeners.forEach(f => { try { f(state); } catch {} }); }
export function patch(next){ Object.assign(state, next); saveCache(); emit(); }

/* ---------- кеш ---------- */
export function saveCache(){
  store.set("cache", {
    user: state.user, family: state.family, children: state.children,
    activeChildId: state.activeChildId, topics: state.topics, customTopics: state.customTopics,
    progress: state.progress, bestStars: state.bestStars, settings: state.settings, guest: state.guest
  });
}
export function loadCache(){
  const c = store.get("cache", null);
  if (c) Object.assign(state, c, { settings: Object.assign({}, state.settings, c.settings) });
  if (!state.topics.length) state.topics = BUILTIN.map(normalizeBuiltin);
  setLocale(state.settings.childLocale || "kk");
}

/* ---------- нормализация тем ----------
   Внутренний вид темы совпадает с прототипом: {id, title, pic, words:[[text,pic,syllables]]},
   у каждого слова дополнительно w.id — идентификатор для API. */
function word(text, pic, syl, id){
  const w = [text, pic, syl || text];
  w.id = id || null;
  return w;
}
function normalizeBuiltin(t){
  const topic = { id: t.id, slug: t.id, title: t.title, title_kk: t.title, title_ru: t.title, pic: t.pic, kind: "builtin" };
  topic.words = t.words.map(w => word(w[0], w[1], w[2], t.id + ":" + w[0]));
  return topic;
}
export function normalizeApiTopic(t, locale){
  const loc = locale || state.settings.childLocale || "kk";
  const topic = {
    id: t.slug || t.id, slug: t.slug || t.id,
    title: (loc === "ru" ? t.title_ru : t.title_kk) || t.title_kk || t.title_ru || "",
    title_kk: t.title_kk, title_ru: t.title_ru,
    pic: t.pic, kind: t.kind || "builtin", custom: t.kind === "family"
  };
  topic.words = (t.words || []).map(w => word(w.text_kk || w.text || "", w.pic, w.syllables, w.id || (topic.slug + ":" + (w.text_kk || ""))));
  return topic;
}
export const allTopics = () => [...state.customTopics, ...state.topics];
export const topicById = id => allTopics().find(t => t.id === id || t.slug === id) || null;

/* ---------- активный ребёнок ---------- */
export const activeChild = () => state.children.find(c => c.id === state.activeChildId) || null;
export function setActiveChild(id){
  state.activeChildId = id;
  const c = activeChild();
  if (c && c.locale) { state.settings.childLocale = c.locale; setLocale(c.locale); }
  saveCache(); emit();
}

/* ---------- прогресс ---------- */
export const starsFor = w => {
  const byId = w && w.id ? state.progress[w.id] : null;
  if (byId && typeof byId.stars === "number") return byId.stars;
  return state.bestStars[w && w[0]] || 0;
};
export function topicScore(topic){
  const got = topic.words.reduce((a, w) => a + starsFor(w), 0);
  return { got, total: topic.words.length * 3 };
}
/* Локальная запись результата: кеш сразу, сервер — через api.attempts (см. lesson.js) */
export function recordStars(w, stars){
  if (typeof stars !== "number") return;
  if ((state.bestStars[w[0]] || 0) < stars) state.bestStars[w[0]] = stars;
  if (w.id){
    const cur = state.progress[w.id] || { stars: 0, attempts: 0 };
    state.progress[w.id] = { stars: Math.max(cur.stars || 0, stars), attempts: (cur.attempts || 0) + 1 };
  }
  saveCache();
}

/* ---------- настройки ---------- */
export async function setSetting(key, value, { remote = true } = {}){
  state.settings[key] = value;
  saveCache(); emit();
  if (!remote || !hasSession() || !isOnline()) return;
  try {
    if (key === "modelVoice") await api.patchFamily({ model_voice: !!value });
    if (key === "parentLocale") await api.patchMe({ locale: value });
    if (key === "childLocale"){
      const c = activeChild();
      if (c) await api.patchChild(c.id, { locale: value });
    }
  } catch {}
}

/* ---------- загрузка с сервера ---------- */
export async function syncMe(){
  if (!hasSession() || !isOnline()) return false;
  try {
    const me = await api.me();
    state.user = me.user || null;
    state.family = me.family || null;
    state.children = me.children || [];
    state.guest = !!(me.family && me.family.is_guest);
    if (me.family && typeof me.family.model_voice === "boolean") state.settings.modelVoice = me.family.model_voice;
    if (me.user && me.user.locale) state.settings.parentLocale = me.user.locale;
    if (!activeChild() && state.children.length) state.activeChildId = state.children[0].id;
    const c = activeChild();
    if (c && c.locale){ state.settings.childLocale = c.locale; setLocale(c.locale); }
    saveCache(); emit();
    return true;
  } catch { return false; }
}

export async function syncTopics(){
  if (!hasSession() || !isOnline()) return false;
  try {
    const list = await api.topics();
    const full = await Promise.all(list.map(async t => {
      if (t.words) return t;
      try { return await api.topic(t.slug || t.id); } catch { return null; }
    }));
    const topics = full.filter(Boolean).map(t => normalizeApiTopic(t));
    if (topics.length){ state.topics = topics; saveCache(); emit(); }
    return true;
  } catch { return false; }
}

export async function syncProgress(){
  const c = activeChild();
  if (!c || !hasSession() || !isOnline()) return false;
  try {
    const p = await api.progress(c.id);
    state.progress = p || {};
    // подтянем bestStars по текстам слов, чтобы плитки тем считались и офлайн
    allTopics().forEach(t => t.words.forEach(w => {
      const row = w.id ? state.progress[w.id] : null;
      if (row && typeof row.stars === "number" && (state.bestStars[w[0]] || 0) < row.stars) state.bestStars[w[0]] = row.stars;
    }));
    saveCache(); emit();
    return true;
  } catch { return false; }
}

export async function syncToday(){
  const c = activeChild();
  if (!c) return null;
  if (!hasSession() || !isOnline()) return state.today;
  try {
    state.today = await api.today(c.id);
    saveCache(); emit();
    return state.today;
  } catch { return state.today; }
}

export async function signOut(){
  await api.logout().catch(() => {});
  clearTokens();
  Object.assign(state, {
    user: null, family: null, children: [], activeChildId: null,
    progress: {}, bestStars: {}, today: null, guest: false, customTopics: []
  });
  store.del("cache");
  emit();
}

if (typeof window !== "undefined"){
  window.addEventListener("online",  () => { state.online = true;  emit(); });
  window.addEventListener("offline", () => { state.online = false; emit(); });
}
