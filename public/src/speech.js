/* Распознавание речи и оценка произношения — перенесено из прототипа.
   Тексты подсказок переехали в i18n: tipFor возвращает ключ строки. */

export const SR = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
export let activeRec = null;

/* Где мы запущены и что здесь реально работает с микрофоном.
   - iPhone/iPad: все браузеры там на движке Safari, а распознавание речи Apple
     не знает казахского. Поэтому на iOS не распознаём, а записываем ребёнка
     и даём ему послушать себя.
   - Встроенные браузеры Telegram/Instagram/WhatsApp/Facebook часто не дают
     микрофон вовсе — просим открыть страницу в обычном браузере. */
export function micEnv(){
  const nav = typeof navigator !== "undefined" ? navigator : {};
  const ua = nav.userAgent || "";
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && (nav.maxTouchPoints || 0) > 1);
  const android = /Android/i.test(ua);
  const inapp = /Instagram|FBAN|FBAV|FB_IAB|Telegram|WhatsApp|MicroMessenger|Line\/|; wv\)/i.test(ua);
  const secure = typeof window !== "undefined" && window.isSecureContext !== false;
  const canRecord = secure && !!(nav.mediaDevices && nav.mediaDevices.getUserMedia);
  // Safari на Mac тоже распознаёт речь силами Apple — казахского там нет.
  const appleSpeech = ios || (/Safari\//.test(ua) && !/Chrome|Chromium|Edg\/|OPR\/|Firefox/.test(ua));
  const canRecognize = !!SR && !appleSpeech;
  return { ios, android, inapp, secure, canRecord, canRecognize,
           platform: ios ? "ios" : android ? "android" : "desktop" };
}
export function abortListening(){ if (activeRec) { try { activeRec.abort(); } catch {} } }

export function listen(onInterim){
  return new Promise(resolve => {
    if (!SR) return resolve({ error: "unsupported" });
    const r = new SR();
    r.lang = "kk-KZ"; r.interimResults = true; r.maxAlternatives = 5; r.continuous = false;
    let done = false, interim = "";
    const finals = [];
    const finish = o => { if (done) return; done = true; clearTimeout(timer); activeRec = null; try { r.abort(); } catch {} resolve(o); };
    r.onresult = e => {
      for (let i = e.resultIndex; i < e.results.length; i++){
        const res = e.results[i];
        if (res.isFinal){ for (let j = 0; j < res.length; j++) finals.push(res[j].transcript); finish({ alts: finals }); }
        else { interim = res[0].transcript; onInterim && onInterim(interim); }
      }
    };
    r.onerror = e => finish({ error: e.error, alts: interim ? [interim] : [] });
    r.onend = () => finish({ alts: finals.length ? finals : (interim ? [interim] : []) });
    const timer = setTimeout(() => { try { r.stop(); } catch {} }, 7000);
    activeRec = r;
    try { r.start(); } catch { finish({ error: "start" }); }
  });
}

/* ---------- оценка произношения ---------- */
const LOOSE = {"қ":"к","ғ":"г","ң":"н","ө":"о","ұ":"у","ү":"у","і":"и","ы":"и","ә":"а","һ":"х","ё":"е","й":"и"};
const NUMS = {"бір":"1","екі":"2","үш":"3","төрт":"4","бес":"5","алты":"6","жеті":"7","сегіз":"8","тоғыз":"9","он":"10"};
const norm = s => String(s).toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, " ").replace(/\s+/g, " ").trim();
const loose = s => [...s].map(c => LOOSE[c] || c).join("");

function lev(a, b){
  a = [...a]; b = [...b];
  const d = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++){
    let prev = d[0]; d[0] = i;
    for (let j = 1; j <= b.length; j++){
      const t = d[j];
      d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = t;
    }
  }
  return d[b.length];
}
const sim = (a, b) => { const m = Math.max([...a].length, [...b].length); return m ? 1 - lev(a, b) / m : 0; };

export function score(target, alts){
  const t = norm(target);
  let best = { stars: 0, heard: alts[0] ? norm(alts[0]) : "", s: -1, tok: "" };
  for (const alt of alts){
    const n = norm(alt);
    for (const tok of new Set([n, ...n.split(/[\s-]+/)])){
      if (!tok) continue;
      let st = 0;
      if (tok === t || (NUMS[t] && tok === NUMS[t])) st = 3;
      else if ([...t].length >= 3 && tok.startsWith(t) && [...tok].length - [...t].length <= 3) st = 3;
      else {
        const s1 = sim(tok, t), s2 = sim(loose(tok), loose(t));
        if (s2 === 1 || s1 >= 0.75) st = 2; else if (s2 >= 0.6) st = 1;
      }
      const s = sim(loose(tok), loose(t));
      if (st > best.stars || (st === best.stars && s > best.s)) best = { stars: st, heard: n, s, tok };
    }
  }
  return best;
}

const TIP_LETTERS = ["қ", "ғ", "ң", "ө", "ұ", "ү", "і", "ә", "ы"];
/* Возвращает ключ i18n вида "tip_қ" либо null. */
export function tipFor(target, heardTok){
  for (const c of target) if (TIP_LETTERS.includes(c) && !(heardTok || "").includes(c)) return "tip_" + c;
  return null;
}
