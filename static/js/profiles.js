/* کاربران: صفحهٔ ورود، فهرست بالای صفحه و پنجرهٔ پروفایل. */

import { $, api, el, showMessage, t } from "./core.js";

// تصویرهای آماده: بدون فایل و بدون اینترنت
const AVATARS = {
  a1: ["🦊", "#f97316"], a2: ["🐼", "#64748b"], a3: ["🦉", "#a16207"], a4: ["🐢", "#16a34a"],
  a5: ["🐙", "#db2777"], a6: ["🦁", "#d97706"], a7: ["🐝", "#ca8a04"], a8: ["🐬", "#0284c7"],
  a9: ["🌵", "#15803d"], a10: ["🌙", "#4f46e5"], a11: ["🚀", "#7c3aed"], a12: ["📚", "#0d9488"],
};

let info = null;       // فهرست کاربران
let editing = null;    // { id یا null برای کاربر تازه, avatar, photo, removePhoto }

export function avatarOf(profile, extraClass = "") {
  if (profile.has_photo) {
    return el("img", { class: `avatar ${extraClass}`, src: `/api/profiles/${profile.id}/photo?v=${photoVersion}`, alt: "" });
  }
  const [emoji, color] = AVATARS[profile.avatar] || AVATARS.a1;
  return el("span", { class: `avatar ${extraClass}`, style: `background:${color}`, "aria-hidden": "true" }, emoji);
}

// با عوض شدن عکس، مرورگر نسخهٔ قبلی را از حافظه نشان ندهد
let photoVersion = 0;

export async function loadProfiles() {
  info = await (await fetch("/api/profiles")).json();
  return info;
}

function activeProfile() {
  return info.profiles.find((profile) => profile.id === info.active);
}

// ---------- ورود

/** ورود با یک کاربر. اگر رمز داشته باشد، اول رمز می‌پرسد. */
async function enter(profile, password = "") {
  try {
    await api("POST", "/api/profiles/login", { id: profile.id, password });
    window.location.reload();
  } catch (error) { /* پیام خطا نشان داده شده است */ }
}

function choose(profile) {
  if (!profile.has_password) {
    enter(profile);
    return;
  }
  const box = $("#password-box");
  box.hidden = false;
  $("#password-name").replaceChildren(avatarOf(profile, "large"), el("strong", {}, profile.name));
  const input = $("#password-input");
  input.value = "";
  input.focus();
  box.onsubmit = (e) => {
    e.preventDefault();
    enter(profile, input.value);
  };
}

function profileTiles() {
  return [
    ...info.profiles.map((profile) => el("button", {
      type: "button", class: "profile-tile", "data-profile": profile.id, onclick: () => choose(profile),
    }, avatarOf(profile, "large"), el("strong", {}, profile.name), profile.has_password && el("span", { class: "muted small" }, "🔒"))),
    el("button", { type: "button", id: "login-add", class: "profile-tile", onclick: () => openProfileDialog(null) },
      el("span", { class: "avatar large add" }, "+"), el("strong", {}, t("کاربر جدید"))),
  ];
}

/** صفحهٔ ورود: وقتی چند کاربر هست یا تنها کاربر رمز دارد */
export function showLogin() {
  document.body.classList.add("logged-out");
  $("#login-tiles").replaceChildren(...profileTiles());
  $("#password-box").hidden = true;
  $("#login-screen").hidden = false;
  if (info.profiles.length === 1) choose(info.profiles[0]);
}

// ---------- فهرست بالای صفحه

export function renderProfileButton() {
  const profile = activeProfile();
  $("#profile-button").replaceChildren(avatarOf(profile), el("span", { class: "profile-name" }, profile.name));
}

function openMenu() {
  const menu = $("#profile-menu");
  if (!menu.hidden) {
    menu.hidden = true;
    return;
  }
  menu.replaceChildren(
    ...info.profiles.map((profile) => {
      const isActive = profile.id === info.active;
      return el("div", { class: `profile-row${isActive ? " current" : ""}`, "data-profile": profile.id },
        el("button", {
          type: "button", class: "ghost profile-pick",
          onclick: () => {
            menu.hidden = true;
            if (isActive) return;
            if (profile.has_password) openPasswordDialog(profile);
            else enter(profile);
          },
        }, avatarOf(profile), el("span", {}, profile.name), profile.has_password && el("span", { class: "small" }, "🔒")),
        isActive && el("button", {
          type: "button", class: "icon profile-edit", title: t("تنظیمات پروفایل"), "aria-label": t("تنظیمات پروفایل"),
          onclick: () => { menu.hidden = true; openProfileDialog(profile); },
        }, "⚙"));
    }),
    el("button", {
      type: "button", id: "profile-add", class: "ghost profile-pick",
      onclick: () => { menu.hidden = true; openProfileDialog(null); },
    }, el("span", { class: "avatar add" }, "+"), el("span", {}, t("کاربر جدید"))),
  );
  menu.hidden = false;
}

function openPasswordDialog(profile) {
  document.body.classList.add("logged-out");
  $("#login-tiles").replaceChildren();
  $("#login-screen").hidden = false;
  $("#login-cancel").hidden = false;
  choose(profile);
}

// ---------- پنجرهٔ پروفایل

function openProfileDialog(profile) {
  editing = { id: profile ? profile.id : null, avatar: profile ? profile.avatar : "a1", photo: null, removePhoto: false, profile };
  const f = $("#profile-form").elements;
  $("#profile-title").textContent = profile ? t("تنظیمات پروفایل") : t("کاربر جدید");
  f.name.value = profile ? profile.name : "";
  f.password.value = "";
  f.password.placeholder = profile && profile.has_password ? t("خالی = بدون تغییر") : t("خالی = بدون رمز");
  $("#profile-remove-password").hidden = !(profile && profile.has_password);
  $("#profile-remove-password-box").checked = false;
  $("#profile-delete").hidden = !profile || profile.is_main || info.profiles.length < 2;
  $("#profile-photo-input").value = "";
  renderPicker();
  $("#profile-dialog").showModal();
  f.name.focus();
}

function renderPicker() {
  const showPhoto = editing.photo || (editing.profile && editing.profile.has_photo && !editing.removePhoto);
  $("#profile-preview").replaceChildren(editing.photo
    ? el("img", { class: "avatar large", src: editing.photo, alt: "" })
    : avatarOf({ ...(editing.profile || {}), id: editing.id, avatar: editing.avatar, has_photo: Boolean(showPhoto) }, "large"));
  $("#profile-photo-remove").hidden = !showPhoto;
  $("#profile-avatars").replaceChildren(...Object.keys(AVATARS).map((key) => el("button", {
    type: "button", class: `avatar-choice${key === editing.avatar && !showPhoto ? " selected" : ""}`, "data-avatar": key,
    onclick: () => {
      editing.avatar = key;
      editing.photo = null;
      editing.removePhoto = Boolean(editing.profile && editing.profile.has_photo);
      renderPicker();
    },
  }, avatarOf({ avatar: key, has_photo: false }))));
}

/** عکس قبل از فرستادن کوچک می‌شود تا حجمش کم بماند */
function shrinkPhoto(file) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const side = Math.min(image.width, image.height);
      const canvas = el("canvas", { width: 256, height: 256 });
      canvas.getContext("2d").drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side, 0, 0, 256, 256);
      URL.revokeObjectURL(image.src);
      resolve(canvas.toDataURL("image/jpeg", 0.88));
    };
    image.onerror = () => reject(new Error(t("این فایل عکس نیست.")));
    image.src = URL.createObjectURL(file);
  });
}

$("#profile-photo-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    editing.photo = await shrinkPhoto(file);
    editing.removePhoto = false;
    renderPicker();
  } catch (error) {
    showMessage(error.message);
  }
});

$("#profile-photo-remove").addEventListener("click", () => {
  editing.photo = null;
  editing.removePhoto = true;
  renderPicker();
});

$("#profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target.elements;
  const data = { name: f.name.value.trim(), avatar: editing.avatar };
  if (editing.photo) data.photo = editing.photo;
  if (editing.id) {
    if (editing.removePhoto) data.remove_photo = true;
    if ($("#profile-remove-password-box").checked) data.password = "";
    else if (f.password.value) data.password = f.password.value;
    await api("PATCH", `/api/profiles/${editing.id}`, data);
    photoVersion += 1;
    await loadProfiles();
    renderProfileButton();
    $("#profile-dialog").close();
  } else {
    if (f.password.value) data.password = f.password.value;
    await api("POST", "/api/profiles", data);
    window.location.reload();
  }
});

$("#profile-delete").addEventListener("click", async () => {
  const { profile } = editing;
  if (!confirm(t("کاربر «{0}» حذف شود؟ داده‌هایش پاک نمی‌شوند و به پوشهٔ profiles-deleted می‌روند.", profile.name))) return;
  await api("DELETE", `/api/profiles/${profile.id}`);
  window.location.reload();
});

$("#close-profile").addEventListener("click", () => $("#profile-dialog").close());

$("#profile-button").addEventListener("click", (e) => {
  e.stopPropagation();
  openMenu();
});

document.addEventListener("pointerdown", (e) => {
  if (!e.target.closest("#profile-menu, #profile-button")) $("#profile-menu").hidden = true;
});

$("#login-cancel").addEventListener("click", () => {
  document.body.classList.remove("logged-out");
  $("#login-screen").hidden = true;
  $("#login-cancel").hidden = true;
});
