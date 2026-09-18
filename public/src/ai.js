/* AI-разделы (window.claude → sample). Если window.claude нет, блоки просто скрыты:
   sampleP резолвится в null и ни setupAI, ни askTeacher не вызываются. */

import { state, saveCache, emit } from "./state.js";
import { api, hasSession, isOnline } from "./api.js";
import { t } from "./i18n.js";
import { $, esc, ICON } from "./ui.js";
import { currentGen } from "./main.js";

let status = "";
export const aiStatus = () => status;
export const setAiStatus = s => { status = s; };

/* ---------- «Ұстаз» придумывает тему ---------- */
export function setupAI(sample, rerender){
  const band = $("#aiBand"); if (!band) return;
  band.hidden = false;
  const form = $("#aiForm"), input = $("#aiTheme"), go = $("#aiGo"), statusEl = $("#aiStatus");
  band.querySelectorAll(".chip").forEach(c => c.onclick = () => { input.value = c.dataset.chip; form.requestSubmit(); });
  form.onsubmit = async e => {
    e.preventDefault();
    const theme = input.value.trim();
    if (!theme){ statusEl.textContent = t("ai_need_theme"); input.focus(); return; }
    go.disabled = true; statusEl.textContent = t("ai_working");
    const g = currentGen();
    const prompt = `You create vocabulary sets for a Kazakh-language learning site for children aged 6–8. The whole interface is in Kazakh.
Theme requested by the child or parent (may be written in any language): "${theme.replace(/"/g, "'")}"

Give exactly 8 simple, common, concrete nouns that a 6–8-year-old can easily picture, belonging to this theme.
Rules:
- Correct standard literary Kazakh in Cyrillic, lowercase, singular, one word each (no spaces).
- Prefer native Kazakh words over Russian loanwords when a Kazakh word is in everyday use.
- Each word gets ONE emoji that clearly depicts that exact object; no duplicate emojis.
- Split each word into syllables by Kazakh rules, joined with hyphens (e.g. "ал-ма", "құл-пы-най"); joining the syllables must give the word exactly.
- If the theme is inappropriate for young children, use the theme "Ойыншықтар" instead.
Reply with only JSON, no prose:
{"title":"Short Kazakh topic name, first letter capital","emoji":"one emoji","words":[{"word":"алма","emoji":"🍎","syllables":"ал-ма"}]}`;
    try {
      const data = await sample.json(prompt, { modelTier: "default" });
      if (g !== currentGen()) return;
      const words = (Array.isArray(data?.words) ? data.words : [])
        .filter(x => x && typeof x.word === "string" && x.word.trim())
        .slice(0, 8)
        .map(x => {
          const word = x.word.trim().toLowerCase();
          const syl = typeof x.syllables === "string" && x.syllables.replace(/-/g, "") === word ? x.syllables : word;
          return [word, typeof x.emoji === "string" ? x.emoji.slice(0, 8) : "✨", syl];
        });
      if (words.length < 4) throw { code: "shape" };
      const id = "c" + Date.now();
      const topic = {
        id, slug: id, custom: true, kind: "family",
        title: String(data.title || theme).slice(0, 30),
        pic: typeof data.emoji === "string" ? data.emoji.slice(0, 8) : "✨",
        words: words.map(w => { const a = [w[0], w[1], w[2]]; a.id = id + ":" + w[0]; return a; })
      };
      state.customTopics = [topic, ...state.customTopics].slice(0, 6);
      saveCache(); emit();
      pushTopic(topic);
      status = t("ai_ready", { title: topic.title });
      rerender && rerender();
    } catch (err){
      if (g !== currentGen()) return;
      go.disabled = false;
      if (err && err.code === "not_granted"){ band.hidden = true; return; }
      statusEl.textContent = err && err.code === "rate_limited" ? t("ai_busy") : t("ai_failed");
    }
  };
}

/* Своя тема уезжает на сервер, если есть сеть и аккаунт; иначе живёт в кеше. */
async function pushTopic(topic){
  if (!hasSession() || !isOnline()) return;
  try {
    await api.addTopic({
      title_kk: topic.title, title_ru: topic.title, pic: topic.pic,
      words: topic.words.map(w => ({ text_kk: w[0], text_ru: w[0], syllables: w[2], pic: w[1], audio_key: "w:" + w[0] }))
    });
  } catch {}
}

/* ---------- «Ұстаздан хат» на экране итогов ---------- */
export async function askTeacher(sample, L, onPractice){
  const g = currentGen();
  if (!sample) return;
  const box = $("#teacher"); if (!box) return;
  box.hidden = false;
  const { topic, words, results } = L;
  const rows = words.map((w, k) => ({ word: w[0], stars: typeof results[k] === "number" ? results[k] : null }));
  const prompt = `You are a warm, encouraging Kazakh-language teacher for children aged 6–8. A child just finished a word lesson on the topic "${topic.title}".
Each target word was said into a microphone; a speech recognizer gave 0–3 stars (3 = clearly correct, null = not checked).
Results: ${JSON.stringify(rows)}

Write in simple, correct literary Kazakh (Cyrillic) that a 7-year-old understands. Short sentences. No Russian or English words. Speak to the child directly ("сен").
Reply with only JSON, no prose:
{"praise":"1–2 short sentences praising something specific about this result","tip":"one concrete, playful pronunciation tip (max 20 words) about a sound in the weakest word; if every word has 3 stars, instead suggest a fun way to use these words at home","practice":["up to 3 target words from the list to practise again, weakest first; empty array if all have 3 stars"]}`;
  try {
    const data = await sample.json(prompt, { modelTier: "quick" });
    if (g !== currentGen()) return;
    const p = $("#tPraise"), tip = $("#tTip"), pr = $("#tPractice");
    p.classList.remove("wait");
    p.textContent = typeof data?.praise === "string" ? data.praise : t("l_good");
    if (typeof data?.tip === "string" && data.tip.trim()){ tip.textContent = data.tip; tip.hidden = false; }
    const practice = (Array.isArray(data?.practice) ? data.practice : [])
      .map(x => words.find(w => w[0] === String(x).trim().toLowerCase())).filter(Boolean).slice(0, 3);
    if (practice.length){
      const b = document.createElement("button");
      b.type = "button"; b.className = "btn plum small";
      b.innerHTML = ICON.repeat + t("teacher_practice") + practice.map(w => esc(w[0])).join(", ");
      b.onclick = () => onPractice && onPractice(practice);
      pr.appendChild(b);
    }
  } catch (err){
    if (g !== currentGen()) return;
    if (err && err.code === "not_granted"){ box.hidden = true; return; }
    const p = $("#tPraise"); p.classList.remove("wait");
    p.textContent = t("teacher_failed");
  }
}
