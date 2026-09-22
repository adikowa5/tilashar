/* Клиент Tilashar API v1 (docs/api.md).
   — токены в localStorage, автообновление по refresh;
   — офлайн-очередь записей в localStorage и досылка при появлении сети. */

export const BASE = "/api/v1";

const K_TOKENS = "tilashar:tokens";
const K_QUEUE  = "tilashar:queue";

/* ---------- маленькое безопасное хранилище ---------- */
export const store = {
  get(k, d){ try { const v = localStorage.getItem("tilashar:" + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v){ try { localStorage.setItem("tilashar:" + k, JSON.stringify(v)); } catch {} },
  del(k){ try { localStorage.removeItem("tilashar:" + k); } catch {} }
};
const raw = {
  get(k, d){ try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v){ try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  del(k){ try { localStorage.removeItem(k); } catch {} }
};

export class ApiError extends Error {
  constructor(code, status){ super(code); this.code = code; this.status = status || 0; }
}

/* ---------- токены ---------- */
let tokens = raw.get(K_TOKENS, null);
const tokenListeners = new Set();
export function onTokens(fn){ tokenListeners.add(fn); return () => tokenListeners.delete(fn); }
function emitTokens(){ tokenListeners.forEach(f => { try { f(tokens); } catch {} }); }

export function getTokens(){ return tokens; }
export function hasSession(){ return !!(tokens && tokens.access_token); }
export function setTokens(pair){
  tokens = pair && pair.access_token ? pair : null;
  if (tokens) raw.set(K_TOKENS, tokens); else raw.del(K_TOKENS);
  emitTokens();
  return tokens;
}
export function clearTokens(){ setTokens(null); }

/* ---------- сеть ---------- */
export const isOnline = () => (typeof navigator === "undefined" ? true : navigator.onLine !== false);

let refreshing = null;
async function refresh(){
  if (!tokens || !tokens.refresh_token) throw new ApiError("token_invalid", 401);
  if (!refreshing){
    refreshing = call("/auth/refresh", { method: "POST", body: { refresh_token: tokens.refresh_token }, auth: false })
      .then(pair => setTokens(pair))
      .catch(err => { clearTokens(); throw err; })
      .finally(() => { refreshing = null; });
  }
  return refreshing;
}

/* низкоуровневый вызов, без повтора */
async function call(path, { method = "GET", body, form, auth = true, headers } = {}){
  const h = Object.assign({ "Accept": "application/json" }, headers || {});
  if (auth && tokens && tokens.access_token) h["Authorization"] = "Bearer " + tokens.access_token;
  let payload;
  if (form) payload = form;                       // FormData — заголовок Content-Type ставит браузер
  else if (body !== undefined){ h["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch(BASE + path, { method, headers: h, body: payload });
  } catch {
    throw new ApiError("offline", 0);
  }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok){
    const code = (data && (data.detail || data.code)) || ("http_" + res.status);
    throw new ApiError(typeof code === "string" ? code : "http_" + res.status, res.status);
  }
  return data;
}

/* вызов с автообновлением токена */
export async function request(path, opts = {}){
  try {
    return await call(path, opts);
  } catch (err){
    const retriable = err instanceof ApiError && err.status === 401 && opts.auth !== false && tokens && tokens.refresh_token;
    if (!retriable) throw err;
    await refresh();
    return call(path, opts);
  }
}

/* ---------- офлайн-очередь ---------- */
let queue = raw.get(K_QUEUE, []);
const queueListeners = new Set();
export function onQueue(fn){ queueListeners.add(fn); return () => queueListeners.delete(fn); }
const saveQueue = () => { raw.set(K_QUEUE, queue); queueListeners.forEach(f => { try { f(queue.length); } catch {} }); };
export const queueSize = () => queue.length;

export function enqueue(op){
  queue.push(Object.assign({ id: Date.now() + ":" + Math.random().toString(36).slice(2, 8) }, op));
  if (queue.length > 200) queue = queue.slice(-200);
  saveQueue();
}

let flushing = false;
export async function flushQueue(){
  if (flushing || !queue.length || !isOnline() || !hasSession()) return;
  flushing = true;
  try {
    while (queue.length){
      const op = queue[0];
      try {
        await request(op.path, { method: op.method || "POST", body: op.body });
      } catch (err){
        if (err instanceof ApiError && err.status === 0) break;      // нет сети — ждём
        if (err instanceof ApiError && err.status === 401) break;    // нет сессии — ждём входа
        // всё остальное (400/404/422) не вылечится повтором — выкидываем
      }
      queue.shift(); saveQueue();
    }
  } finally { flushing = false; }
}
if (typeof window !== "undefined"){
  window.addEventListener("online", () => { flushQueue(); });
  onTokens(tk => { if (tk) flushQueue(); });
}

/* ---------- методы контракта ---------- */
export const api = {
  /* вход без регистрации: новое устройство — гость, второе устройство — по коду семьи */
  guest:      ()   => request("/auth/guest", { method: "POST", auth: false }).then(setTokens),
  join:       code => request("/auth/join",  { method: "POST", body: { code }, auth: false }).then(setTokens),
  familyCode: ()   => request("/family/code"),
  newFamilyCode: () => request("/family/code", { method: "POST" }),
  logout:    async () => {
    const rt = tokens && tokens.refresh_token;
    try { if (rt) await request("/auth/logout", { method: "POST", body: { refresh_token: rt } }); } catch {}
    clearTokens();
  },

  /* я и семья */
  me:          ()      => request("/me"),
  patchMe:     patch   => request("/me",     { method: "PATCH", body: patch }),
  patchFamily: patch   => request("/family", { method: "PATCH", body: patch }),

  /* дети */
  children:    ()            => request("/children"),
  addChild:    child         => request("/children", { method: "POST", body: child }),
  patchChild:  (id, patch)   => request("/children/" + encodeURIComponent(id), { method: "PATCH", body: patch }),
  removeChild: id            => request("/children/" + encodeURIComponent(id), { method: "DELETE" }),

  /* контент: весь опубликованный материал одним запросом, без токена */
  catalog:   ()     => request("/content/catalog", { auth: false }),
  topics:    ()     => request("/content/topics"),
  topic:     slug   => request("/content/topics/" + encodeURIComponent(slug)),
  addTopic:  topic  => request("/content/topics", { method: "POST", body: topic }),

  /* день и прогресс */
  today:     id => request("/children/" + encodeURIComponent(id) + "/today"),
  progress:  id => request("/children/" + encodeURIComponent(id) + "/progress"),
  /* попытки: в офлайне кладём в очередь и отвечаем null */
  attempts: async (id, list) => {
    const path = "/children/" + encodeURIComponent(id) + "/attempts";
    const body = list.slice(0, 50);
    if (!body.length) return null;
    if (!isOnline() || !hasSession()){ enqueue({ path, method: "POST", body }); return null; }
    try {
      const out = await request(path, { method: "POST", body });
      flushQueue();
      return out;
    } catch (err){
      if (err instanceof ApiError && (err.status === 0 || err.status === 401)){ enqueue({ path, method: "POST", body }); return null; }
      throw err;
    }
  },

  /* голос родителя */
  voices:    ()  => request("/voices"),
  putVoice:  (key, blob, name) => {
    const fd = new FormData();
    fd.append("key", key);
    fd.append("file", blob, name || "voice.wav");
    return request("/voices", { method: "PUT", form: fd });
  },
  delVoice:  key => request("/voices/" + encodeURIComponent(key), { method: "DELETE" }),

  /* прочее */
  health: () => request("/health", { auth: false }),
  config: () => request("/config", { auth: false })
};

export default api;
