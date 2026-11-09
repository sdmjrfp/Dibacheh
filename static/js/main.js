/* نقطهٔ شروع صفحه. */

import "./add-menu.js";
import "./calendar.js";
import "./item-dialog.js";
import "./layout.js";
import "./settings.js";
import "./setup.js";
import "./sources.js";
import "./splitter.js";
import "./stats.js";

import { $, api, setRenderer, showMessage, t } from "./core.js";
import { loadProfiles, renderProfileButton, showLogin } from "./profiles.js";
import { renderNow } from "./render.js";

$("#undo-button").addEventListener("click", async () => {
  const result = await api("POST", "/api/undo", {});
  if (result.undone) showMessage(t("برگشت: {0}", result.undone), false);
});

$("#redo-button").addEventListener("click", async () => {
  const result = await api("POST", "/api/redo", {});
  if (result.redone) showMessage(t("دوباره انجام شد: {0}", result.redone), false);
});

setRenderer(renderNow);

// اگر ورود لازم باشد، تا وارد نشود هیچ داده‌ای خوانده نمی‌شود
const profileInfo = await loadProfiles();
if (profileInfo.login_required) {
  showLogin();
} else {
  renderProfileButton();
  api("GET", "/api/state");
}
