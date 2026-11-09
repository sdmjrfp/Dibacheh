"""مسیرهای نسخهٔ تازه و تغییرات نسخه."""

from pathlib import Path

from flask import Blueprint, jsonify, request

import config
import database
import platform_tools
from errors import UserError
from i18n import _
from services import update
from webutil import body, get_db

bp = Blueprint("update", __name__)


@bp.route("/api/update/check")
def api_update_check():
    """صفحه این را در پس‌زمینه صدا می‌زند و منتظر جوابش نمی‌ماند."""
    if not database.get_settings(get_db())["check_updates"]:
        return jsonify({"available": False, "disabled": True})
    return jsonify(update.check(config.VERSION, request.args.get("lang", "fa")))


@bp.route("/api/update/download", methods=["POST"])
def api_update_download():
    result = update.check(config.VERSION, body().get("lang", "fa"))
    if not result.get("available"):
        raise UserError(_("نسخهٔ تازه‌ای برای دانلود نیست."))
    update.start_download(result["asset"])
    return jsonify(update.progress)


@bp.route("/api/update/progress")
def api_update_progress():
    return jsonify(update.progress)


def _downloaded_file():
    path = update.progress.get("path")
    if update.progress.get("state") != "done" or not path or not Path(path).is_file():
        raise UserError(_("فایل دانلودشده پیدا نشد."))
    return Path(path)


@bp.route("/api/update/reveal", methods=["POST"])
def api_update_reveal():
    platform_tools.launch(platform_tools.reveal_args(_downloaded_file()))
    return jsonify({"ok": True})


@bp.route("/api/update/open", methods=["POST"])
def api_update_open():
    platform_tools.launch(platform_tools.open_args(_downloaded_file()))
    return jsonify({"ok": True})


@bp.route("/api/update/seen", methods=["POST"])
def api_update_seen():
    """کاربر تغییرات این نسخه را دید؛ دفعهٔ بعد نشان داده نمی‌شود."""
    database.set_setting(get_db(), "last_seen_version", config.VERSION)
    return jsonify({"ok": True})
