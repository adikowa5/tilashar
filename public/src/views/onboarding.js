/* Вход: телефон → код → имя ребёнка и возраст.
   Плюс «попробовать без регистрации» — гостевая семья (POST /auth/guest). */

import { navigate, viewEl, goAfterAuth } from "../main.js";
import { api, hasSession, ApiError } from "../api.js";
import { state, syncMe, syncTopics, setActiveChild, patch } from "../state.js";
import { t } from "../i18n.js";
import { ICON, $, esc, AVATARS, avatarHTML } from "../ui.js";

let form = { step: "phone", phone: "", dev: null };

const cleanPhone = s => String(s || "").replace(/[\s()-]/g, "");
const phoneOk = s => /^\+?\d{10,15}$/.test(cleanPhone(s));

const ERR = {
  phone_invalid: "err_phone_invalid", code_invalid: "err_code_invalid", code_expired: "err_code_expired",
  code_not_found: "err_code_not_found", too_many_attempts: "err_too_many", already_claimed: "err_already_claimed",
  age_out_of_range: "err_age_range", too_many_children: "err_too_many_children", offline: "err_network"
};
const errText = e => t(ERR[e && e.code] || "err_save");

export function render(params){
  if (params && params.step) form.step = params.step;
  if (!hasSession() && form.step === "child") form.step = "phone";
  if (form.step === "child") return renderChild();
  if (form.step === "code") return renderCode();
  renderPhone();
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

/* ---------- шаг 1: телефон ---------- */
function renderPhone(){
  shell(`
    <h1>${t("app_title")}</h1>
    <h2>${t("ob_phone_head")}</h2>
    <p class="note">${t("ob_phone_note")}</p>
    <form class="ai-form" id="f">
      <div class="ai-row">
        <label class="sr" for="phone">${t("ob_phone_label")}</label>
        <input id="phone" inputmode="tel" autocomplete="tel" value="${esc(form.phone)}" placeholder="${t("ob_phone_ph")}">
        <button class="btn primary" id="send" type="submit">${t("ob_send_code")}${ICON.arrow}</button>
      </div>
      <p class="status" id="st"></p>
    </form>
    <div class="gate-foot">
      <button class="btn" id="guest" type="button">${t("ob_guest")}</button>
      <p class="note">${t("ob_guest_note")}</p>
    </div>`);

  const input = $("#phone"), st = $("#st"), send = $("#send");
  $("#f").onsubmit = async e => {
    e.preventDefault();
    const num = cleanPhone(input.value);
    if (!phoneOk(num)){ st.textContent = t("err_phone_invalid"); input.focus(); return; }
    send.disabled = true; st.textContent = "";
    try {
      const out = await api.sendCode(num);
      form.phone = num;
      form.dev = out && out.dev_code ? out.dev_code : null;
      form.step = "code";
      renderCode();
    } catch (err){ st.textContent = errText(err); send.disabled = false; }
  };
  $("#guest").onclick = async () => {
    const btn = $("#guest"); btn.disabled = true; st.textContent = "";
    try {
      await api.guest();
      await syncMe();
      syncTopics();
      patch({ guest: true });
      form.step = "child";
      renderChild();
    } catch (err){
      // Без сервера гость всё равно должен попасть в урок — работаем на встроенном контенте.
      st.textContent = errText(err);
      btn.disabled = false;
      patch({ guest: true });
      navigate("today");
    }
  };
}

/* ---------- шаг 2: код ---------- */
function renderCode(){
  shell(`
    <h2>${t("ob_code_head")}</h2>
    <p class="note">${esc(t("ob_code_note", { phone: form.phone }))}</p>
    <form class="ai-form" id="f">
      <div class="ai-row">
        <label class="sr" for="code">${t("ob_code_label")}</label>
        <input id="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="${t("ob_code_ph")}">
        <button class="btn primary" id="ok" type="submit">${t("ob_confirm")}${ICON.arrow}</button>
      </div>
      <p class="status" id="st">${form.dev ? esc(t("ob_dev_code", { code: form.dev })) : ""}</p>
    </form>
    <div class="gate-foot">
      <button class="btn ghost small" id="back" type="button">${ICON.back}${t("back")}</button>
      <button class="btn ghost small" id="resend" type="button">${t("ob_resend")}</button>
    </div>`);

  const code = $("#code"), st = $("#st"), ok = $("#ok");
  code.focus();
  $("#f").onsubmit = async e => {
    e.preventDefault();
    ok.disabled = true;
    try {
      await api.token(form.phone, code.value.trim());
      await syncMe();
      syncTopics();
      if (state.children.length){
        setActiveChild(state.children[0].id);
        goAfterAuth();
      } else {
        form.step = "child";
        renderChild();
      }
    } catch (err){ st.textContent = errText(err); ok.disabled = false; }
  };
  $("#back").onclick = () => { form.step = "phone"; renderPhone(); };
  $("#resend").onclick = async () => {
    try { const out = await api.sendCode(form.phone); st.textContent = out && out.dev_code ? t("ob_dev_code", { code: out.dev_code }) : ""; }
    catch (err){ st.textContent = errText(err); }
  };
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
    form.step = "phone";
    navigate("today");
  });
}
