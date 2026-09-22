/* Тілашар — service worker.
   Оболочка и контент (включая пак озвучки) кладутся в кеш при установке:
   в офлайне приложение открывается и даёт пройти урок.
   Код и стили — network-first с таймаутом: новый деплой виден со следующей загрузки,
   а без сети всё берётся из кеша. /api — network-first с кешем на GET. */

const VERSION = "tilashar-v2";
const NET_TIMEOUT_MS = 3500;
const SHELL = VERSION + "-shell";
const RUNTIME = VERSION + "-runtime";

const PRECACHE = [
  "./",
  "./index.html",
  "./styles.css",
  "./manifest.webmanifest",
  "./icons/icon-192.svg",
  "./icons/icon-512.svg",
  "./src/main.js",
  "./src/api.js",
  "./src/state.js",
  "./src/i18n.js",
  "./src/ui.js",
  "./src/ai.js",
  "./src/audio.js",
  "./src/voices.js",
  "./src/recorder.js",
  "./src/speech.js",
  "./src/ill.js",
  "./src/words.js",
  "./src/audio-pack.js",
  "./src/views/onboarding.js",
  "./src/views/children.js",
  "./src/views/today.js",
  "./src/views/lesson.js",
  "./src/views/results.js",
  "./src/views/studio.js",
  "./src/views/parent.js",
  "./src/views/mic.js"
];

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    const cache = await caches.open(SHELL);
    // по одному: один сбойный файл не должен завалить всю установку
    await Promise.all(PRECACHE.map(u => cache.add(new Request(u, { cache: "reload" })).catch(() => {})));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== SHELL && k !== RUNTIME).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

const isApi = url => url.pathname.startsWith("/api/");
const isMedia = url => url.pathname.startsWith("/media/");
const isFont = url => url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com";

/* network-first: свежие данные, кеш — запасной вариант для GET */
async function networkFirst(req){
  const cache = await caches.open(RUNTIME);
  try {
    const res = await fetch(req);
    if (req.method === "GET" && res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (err){
    if (req.method === "GET"){
      const hit = await cache.match(req);
      if (hit) return hit;
    }
    return new Response(JSON.stringify({ detail: "offline" }), {
      status: 503, headers: { "Content-Type": "application/json" }
    });
  }
}

/* network-first для своей статики: ждём сеть не дольше NET_TIMEOUT_MS, иначе отдаём кеш */
async function freshFirst(req){
  const cache = await caches.open(SHELL);
  const network = fetch(req).then(res => {
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  });
  network.catch(() => {});             // ответ из кеша уже ушёл — поздняя ошибка сети не важна
  const hit = await cache.match(req);
  if (!hit) return network;
  const timeout = new Promise(resolve => setTimeout(() => resolve(null), NET_TIMEOUT_MS));
  try {
    const res = await Promise.race([network, timeout]);
    return res && res.ok ? res : hit;
  } catch {
    return hit;
  }
}

/* cache-first: шрифты и медиа */
async function cacheFirst(req, cacheName){
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req, { ignoreSearch: false });
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res && (res.ok || res.type === "opaque")) cache.put(req, res.clone());
    return res;
  } catch (err){
    const shell = await caches.open(SHELL);
    const fallback = await shell.match("./index.html");
    if (req.mode === "navigate" && fallback) return fallback;
    throw err;
  }
}

self.addEventListener("fetch", e => {
  const req = e.request;
  const url = new URL(req.url);

  if (isApi(url)) return e.respondWith(networkFirst(req));

  if (req.mode === "navigate"){
    return e.respondWith((async () => {
      try { return await fetch(req); }
      catch {
        const shell = await caches.open(SHELL);
        return (await shell.match("./index.html")) || Response.error();
      }
    })());
  }

  if (req.method !== "GET") return;
  if (isFont(url) || isMedia(url)) return e.respondWith(cacheFirst(req, RUNTIME));
  if (url.origin === self.location.origin) return e.respondWith(freshFirst(req));
});

self.addEventListener("message", e => { if (e.data === "skip-waiting") self.skipWaiting(); });
