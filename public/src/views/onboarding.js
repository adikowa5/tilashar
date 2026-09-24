/* Первый запуск без регистрации.
   «Бастау» — новая семья на этом устройстве (POST /auth/guest).
   «Отбасы коды» — подключить это устройство к уже существующей семье (POST /auth/join).
   Ссылка вида /?join=ABCD-2345 сразу открывает ввод кода. */

import { navigate, viewEl, goAfterAuth } from "../main.js";
import { api, hasSession, ApiError } from "../api.js";
import { state, syncMe, syncTopics, syncProgress, setActiveChild, patch } from "../state.js";
import { syncVoices } from "../voices.js";
import { t } from "../i18n.js";
import { ICON, $, esc, AVATARS, avatarHTML } from "../ui.js";

let form = { step: "start", code: "" };

const ERR = {
  code_invalid: "err_code_invalid", too_many_attempts: "err_too_many",
  age_out_of_range: "err_age_range", too_many_children: "err_too_many_children", offline: "err_network"
};
const errText = e => t(ERR[e && e.code] || "err_save");

/* Код из ссылки-приглашения (?join=…) — читаем один раз и убираем из адреса. */
function codeFromLink(){
  try {
    const url = new URL(location.href);
    const code = url.searchParams.get("join");
    if (!code) return "";
    url.searchParams.delete("join");
    history.replaceState(null, "", url.pathname + url.search + url.hash);
    return code;
  } catch { return ""; }
}

export function render(params){
  if (params && params.step) form.step = params.step;
  const linkCode = codeFromLink();
  if (linkCode){ form.code = linkCode; form.step = "join"; }
  if (!hasSession() && form.step === "child") form.step = "start";
  if (form.step === "child") return renderChild();
  if (form.step === "join") return renderJoin();
  renderStart();
}

function shell(inner){
  viewEl().innerHTML = `
  <section class="home gate-wrap">
    <div class="gate patch">
      <p class="eyebrow">${t("ob_eyebrow")}</p>
      ${inner}
    </div>
  </section>`;
}

/* ---------- первый экран ---------- */
function renderStart(){
  shell(`
    <h1>${t("app_title")}</h1>
    <h2>${t("ob_start_head")}</h2>
    <p class="note">${t("ob_start_note")}</p>
    <div class="ai-row">
      <button class="btn primary big" id="start" type="button">${t("ob_start_btn")}${ICON.arrow}</button>
    </div>
    <p class="status" id="st"></p>
    <div class="gate-foot">
      <button class="btn" id="toJoin" type="button">${t("ob_have_code")}</button>
      <p class="note">${t("ob_have_code_note")}</p>
    </div>`);

  const st = $("#st");
  $("#start").onclick = async () => {
    const btn = $("#start"); btn.disabled = true; st.textContent = "";
    try {
      await api.guest();
      await syncMe();
      syncTopics();
      patch({ guest: true });
      form.step = "child";
      renderChild();
    } catch (err){
      // Без сервера ребёнок всё равно попадает в урок — на встроенном материале.
      st.textContent = errText(err);
      btn.disabled = false;
      patch({ guest: true });
      navigate("today");
    }
  };
  $("#toJoin").onclick = () => { form.step = "join"; renderJoin(); };
}

/* ---------- подключение по коду семьи ---------- */
function renderJoin(){
  shell(`
    <h2>${t("ob_join_head")}</h2>
    <p class="note">${t("ob_join_note")}</p>
    <form class="ai-form" id="f">
      <div class="ai-row">
        <label class="sr" for="code">${t("ob_join_label")}</label>
        <input id="code" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="12"
               value="${esc(form.code)}" placeholder="ABCD-2345" class="code-input">
        <button class="btn primary" id="ok" type="submit">${t("ob_join_btn")}${ICON.arrow}</button>
      </div>
      <p class="status" id="st"></p>
    </form>
    <div class="gate-foot">
      <button class="btn ghost small" id="back" type="button">${ICON.back}${t("back")}</button>
    </div>`);

  const code = $("#code"), st = $("#st"), ok = $("#ok");
  if (!form.code) code.focus();
  $("#f").onsubmit = async e => {
    e.preventDefault();
    const value = code.value.trim();
    if (!value){ code.focus(); return; }
    ok.disabled = true; st.textContent = "";
    try {
      await api.join(value);
      form.code = "";
      // Данные прежней семьи этого устройства (если была) больше не наши.
      patch({ progress: {}, bestStars: {}, today: null, activeChildId: null, children: [] });
      await syncMe();
      await Promise.all([syncTopics(), syncProgress(), syncVoices()]);
      patch({ guest: false });
      if (state.children.length){
        setActiveChild(state.activeChildId || state.children[0].id);
        goAfterAuth();
      } else {
        form.step = "child";
        renderChild();
      }
    } catch (err){ st.textContent = errText(err); ok.disabled = false; }
  };
  $("#back").onclick = () => { form.step = "start"; renderStart(); };
}

/* ---------- шаг 3: ребёнок ---------- */
export function childForm(opts = {}){
  const avatar = opts.avatar || AVATARS[0];
  return `
    <form class="ai-form kid-form" id="kidForm">
      <div class="ai-row">
        <label class="sr" for="kidName">${t("ob_name_label")}</label>
        <input id="kidName" maxlength="24" autocomplete="off" placeholder="${t("ob_name_ph")}">
      </div>
      <fieldset class="field">
        <legend>${t("ob_age_label")}</legend>
        <div class="chips" id="ages">
          ${[6,7,8,9].map(a => `<button class="chip" type="button" data-age="${a}" aria-pressed="${a === 7}">${a}</button>`).join("")}
        </div>
      </fieldset>
      <fieldset class="field">
        <legend>${t("ob_avatar_label")}</legend>
        <div class="kids" id="avatars">
          ${AVATARS.map(a => `<button class="kid" type="button" data-avatar="${esc(a)}" aria-pressed="${a === avatar}"><span class="plate">${avatarHTML(a)}</span></button>`).join("")}
        </div>
      </fieldset>
      <div class="ai-row">
        <button class="btn primary" id="kidGo" type="submit">${opts.submit || t("ob_start")}${ICON.arrow}</button>
        ${opts.cancel ? `<button class="btn ghost" id="kidCancel" type="button">${t("ch_cancel")}</button>` : ""}
      </div>
      <p class="status" id="kidStatus"></p>
    </form>`;
}

export function wireChildForm(onSubmit, onCancel){
  let age = 7, avatar = AVATARS[0];
  const pick = (box, attr, set) => {
    box.querySelectorAll("[" + attr + "]").forEach(b => b.onclick = () => {
      box.querySelectorAll("[" + attr + "]").forEach(x => x.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
      set(b.getAttribute(attr));
    });
  };
  pick($("#ages"), "data-age", v => { age = +v; });
  pick($("#avatars"), "data-avatar", v => { avatar = v; });
  const st = $("#kidStatus");
  $("#kidForm").onsubmit = async e => {
    e.preventDefault();
    const name = $("#kidName").value.trim();
    if (!name){ st.textContent = t("err_name_required"); $("#kidName").focus(); return; }
    $("#kidGo").disabled = true; st.textContent = "";
    try { await onSubmit({ name, age, avatar, locale: state.settings.childLocale || "kk" }); }
    catch (err){ st.textContent = errText(err); $("#kidGo").disabled = false; }
  };
  if (onCancel && $("#kidCancel")) $("#kidCancel").onclick = onCancel;
}

function renderChild(){
  shell(`
    <h2>${t("ob_child_head")}</h2>
    <p class="note">${t("ob_child_note")}</p>
    ${childForm()}`);
  wireChildForm(async child => {
    let created = null;
    try { created = await api.addChild(child); } catch (err){
      if (err instanceof ApiError && err.status === 0) created = null;   // офлайн — идём на встроенном контенте
      else throw err;
    }
    if (created){
      state.children = [...state.children, created];
      setActiveChild(created.id);
    }
    form.step = "start";
    navigate("today");
  });
}
