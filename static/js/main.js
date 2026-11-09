/* نقطهٔ شروع صفحه. */

import "./calendar.js";
import "./item-dialog.js";
import "./layout.js";
import "./settings.js";
import "./sources.js";
import "./splitter.js";
import "./stats.js";

import { $, api, setRenderer, showMessage } from "./core.js";
import { renderNow } from "./render.js";

$("#vault-button").addEventListener("click", () => api("POST", "/api/browse", { kind: "vault" }));

$("#undo-button").addEventListener("click", async () => {
  const result = await api("POST", "/api/undo", {});
  if (result.undone) showMessage(`برگشت: ${result.undone}`, false);
});

$("#redo-button").addEventListener("click", async () => {
  const result = await api("POST", "/api/redo", {});
  if (result.redone) showMessage(`دوباره انجام شد: ${result.redone}`, false);
});

setRenderer(renderNow);
api("GET", "/api/state");
