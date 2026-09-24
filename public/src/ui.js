/* Иконки и мелкие помощники отрисовки — перенесены из прототипа. */


export const $ = (s, r = document) => r.querySelector(s);
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
export const sleep = ms => new Promise(r => setTimeout(r, ms));
export const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

export const ICON = {
  speaker:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 9h4l5-4v14l-5-4h-4z" fill="currentColor"/><path d="M16 8.5a5 5 0 0 1 0 7M18.8 5.8a8.8 8.8 0 0 1 0 12.4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  mic:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8.5" y="2.5" width="7" height="12" rx="3.5" fill="currentColor"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5v3.5M8.5 21h7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  ear:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 9.5a5.5 5.5 0 0 1 11 0c0 3.3-3.2 4.2-3.2 7.2a3.2 3.2 0 0 1-6.3.6" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"/><path d="M9.8 9.8a2.2 2.2 0 0 1 4.4 0c0 1.6-1.6 2-1.6 3.4" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/></svg>',
  repeat:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 12.5a7.5 7.5 0 0 1 13-5l1.5 1.5M19.5 11.5a7.5 7.5 0 0 1-13 5L5 15" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"/><path d="M19 4v5h-5M5 20v-5h5" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  star:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.6l2.9 5.9 6.4.9-4.7 4.5 1.1 6.4L12 17.3l-5.7 3 1.1-6.4-4.7-4.5 6.4-.9z"/></svg>',
  arrow:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 12h15M13.5 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  back:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19.5 12h-15M10.5 6l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  check:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  play:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/></svg>',
  stop:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor"/></svg>',
  upload:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5V4.5M7 9l5-5 5 5M5 15v3.5h14V15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  trash:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10.2 10.5v6M13.8 10.5v6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  asyk:'<svg viewBox="0 0 24 16" aria-hidden="true"><path d="M2 8c0-3.4 3-4.8 5.4-3.6 1.6.8 7.6.8 9.2 0C19 3.2 22 4.6 22 8s-3 4.8-5.4 3.6c-1.6-.8-7.6-.8-9.2 0C5 12.8 2 11.4 2 8z"/></svg>',
  user:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8.5" r="4" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M4.5 20c1.2-4 4-6 7.5-6s6.3 2 7.5 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  plus:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg>',
  flame:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5c4 4.2 6.5 7.2 6.5 11a6.5 6.5 0 0 1-13 0c0-2.2 1.2-4 2.6-5.6.3 1.6 1.2 2.6 2.4 2.6 1.4 0 2-1.4 1.8-3.2-.1-1.6-.4-3.2-.3-4.8z" fill="currentColor"/></svg>',
  gear:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M12 2.8v2.6M12 18.6v2.6M21.2 12h-2.6M5.4 12H2.8M18.5 5.5l-1.9 1.9M7.4 16.6l-1.9 1.9M18.5 18.5l-1.9-1.9M7.4 7.4 5.5 5.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>'
};

/* ---------- темы и слова ---------- */
const TINT = { animals:"--t-animals", fruits:"--t-fruits", colors:"--t-colors", numbers:"--t-numbers", home:"--t-home", nature:"--t-nature" };
export const tintOf = topic => `var(${TINT[topic && topic.id] || "--t-custom"})`;

/* Что показываем вместо слова: фотография автора, затем цвет или число, затем эмодзи. */
export function picHTML(w){
  if (w && w.img) return `<img class="wpic" src="${esc(w.img)}" alt="" loading="lazy" decoding="async">`;
  const p = String(w[1] || "");
  if (/^#[0-9a-f]{6}$/i.test(p)) return `<span class="swatch" style="--sw:${p}"></span>`;
  if (/^\d{1,2}$/.test(p)) return `<span class="numpic"><span class="numeral">${p}</span><span class="asyks" style="--asz:${p<=2?46:p<=4?32:p<=6?24:18}%">${ICON.asyk.repeat(+p)}</span></span>`;
  return `<span class="emoji" aria-hidden="true">${esc(p)}</span>`;
}
export function topicPic(topic){
  if (topic && topic.img) return `<img class="wpic" src="${esc(topic.img)}" alt="" loading="lazy" decoding="async">`;
  if (topic.pic === "@colors") return `<span class="trio"><i style="background:#E0332B"></i><i style="background:#F5C518"></i><i style="background:#2F6FD6"></i></span>`;
  if (topic.pic === "@numbers") return `<span class="nums">1 2 3</span>`;
  return esc(topic.pic);
}
export const starsRow = (n, cls = "stars") => `<span class="${cls}">${[0,1,2].map(i => ICON.star.replace("<svg", `<svg class="${i < n ? "on" : ""}"`)).join("")}</span>`;
export const sylls = w => String(w[2] || w[0]).split("-");
export function wordHTML(w){
  return sylls(w).map((s, i) => (i ? `<span class="sep" aria-hidden="true">·</span>` : "") + `<span class="syl">${esc(s)}</span>`).join("");
}

/* ---------- войлочное конфетти ---------- */
export function confetti(anchor){
  if (reduced()) return;
  const c = document.createElement("canvas");
  c.className = "confetti"; document.body.appendChild(c);
  const dpr = devicePixelRatio || 1, W = innerWidth, H = innerHeight;
  c.width = W * dpr; c.height = H * dpr;
  const x = c.getContext("2d"); x.scale(dpr, dpr);
  const cs = getComputedStyle(document.documentElement);
  const cols = ["--berry", "--ochre", "--moss", "--plum"].map(v => cs.getPropertyValue(v).trim());
  const r = anchor ? anchor.getBoundingClientRect() : { left: W / 2, top: H / 2, width: 0, height: 0 };
  const ox = r.left + r.width / 2, oy = r.top + r.height / 2;
  const P = Array.from({ length: 70 }, () => ({
    x: ox, y: oy, vx: (Math.random() - .5) * 15, vy: -Math.random() * 13 - 5,
    r: Math.random() * 7 + 5, a: Math.random() * 6, va: (Math.random() - .5) * .35,
    c: cols[Math.random() * cols.length | 0], diamond: Math.random() < .5
  }));
  let t = 0;
  (function frame(){
    x.clearRect(0, 0, W, H);
    for (const p of P){
      p.vy += .42; p.vx *= .985; p.x += p.vx; p.y += p.vy; p.a += p.va;
      x.save(); x.translate(p.x, p.y); x.rotate(p.a); x.fillStyle = p.c;
      if (p.diamond){ x.beginPath(); x.moveTo(0, -p.r / 2); x.lineTo(p.r / 3, 0); x.lineTo(0, p.r / 2); x.lineTo(-p.r / 3, 0); x.closePath(); x.fill(); }
      else { x.beginPath(); x.arc(0, 0, p.r / 2.6, 0, Math.PI * 2); x.fill(); }
      x.restore();
    }
    if (++t < 95) requestAnimationFrame(frame); else c.remove();
  })();
}

/* ---------- AI: window.claude, если он есть ---------- */
export const sampleP = (typeof window !== "undefined" && window.claude && typeof window.claude.use === "function")
  ? window.claude.use("sample").catch(() => null) : Promise.resolve(null);

/* Аватары ребёнка — из того же набора рисунков */
export const AVATARS = ["мысық", "ит", "аю", "қоян", "түйе", "қой"];
const AVATAR_EMOJI = { "мысық": "🐱", "ит": "🐶", "аю": "🐻", "қоян": "🐰", "түйе": "🐫", "қой": "🐑" };
export const avatarHTML = key => `<span class="emoji" aria-hidden="true">${AVATAR_EMOJI[key] || "🙂"}</span>`;
