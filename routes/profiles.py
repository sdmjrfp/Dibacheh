"""مسیرهای کاربران: ورود، عوض کردن کاربر، ساختن و تغییر پروفایل."""

from flask import Blueprint, abort, current_app, jsonify, send_file

import database
import profiles
import undo
import webutil
from errors import UserError
from i18n import _
from webutil import body, get_db

bp = Blueprint("profiles", __name__)


def _main_db():
    return current_app.config["DB_PATH"]


def _after_switch():
    """فهرست برگرداندن و وضعیت backup مال کاربر قبلی است."""
    undo.stack.clear()
    undo.redo_stack.clear()
    webutil.backup_status.update(day=None, problem=None, cloud_problem=None)


def _active_only(profile_id):
    """هر کاربر فقط پروفایل خودش را تغییر می‌دهد؛ وگرنه رمز کاربر دیگر بی‌اثر می‌شد."""
    active = profiles.current(_main_db())
    if active is None or active["id"] != profile_id:
        raise UserError(_("برای تغییر این پروفایل اول با همان کاربر وارد شوید."))


@bp.route("/api/profiles")
def api_profiles():
    return jsonify(profiles.public(_main_db()))


@bp.route("/api/profiles/login", methods=["POST"])
def api_login():
    data = body()
    profiles.login(_main_db(), data.get("id"), data.get("password"))
    _after_switch()
    return jsonify({"ok": True})


@bp.route("/api/profiles", methods=["POST"])
def api_create_profile():
    data = body()
    settings = database.get_settings(get_db())
    profile_id = profiles.create(_main_db(), data.get("name"), data.get("avatar", "a1"), data.get("password"), settings)
    if data.get("photo"):
        profiles.update(_main_db(), profile_id, {"photo": data["photo"]})
    profiles.login(_main_db(), profile_id, data.get("password"))
    _after_switch()
    return jsonify({"id": profile_id})


@bp.route("/api/profiles/<profile_id>", methods=["PATCH"])
def api_update_profile(profile_id):
    _active_only(profile_id)
    profiles.update(_main_db(), profile_id, body())
    return jsonify(profiles.public(_main_db()))


@bp.route("/api/profiles/<profile_id>", methods=["DELETE"])
def api_delete_profile(profile_id):
    _active_only(profile_id)
    profiles.delete(_main_db(), profile_id)
    _after_switch()
    return jsonify(profiles.public(_main_db()))


@bp.route("/api/profiles/<profile_id>/photo")
def api_profile_photo(profile_id):
    path = profiles.photo_path(_main_db(), profile_id)
    if path is None:
        abort(404)
    return send_file(path, mimetype="image/jpeg", max_age=0)
