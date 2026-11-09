"""مسیرهای تنظیمات، دسته‌ها، نوع‌های کار، فونت‌ها و Browse."""

from pathlib import Path

from flask import Blueprint, abort, jsonify, send_file

import database
import sources
from errors import UserError
from i18n import _
from services import data as data_service
from webutil import body, build_state, get_db, state_response

bp = Blueprint("settings", __name__)


@bp.route("/api/browse", methods=["POST"])
def api_browse():
    """پنجرهٔ انتخاب فایل macOS را باز می‌کند.

    kind=file: برای منبع درس. آدرس نسبت به والت یا آدرس کامل برمی‌گردد.
    kind=vault: برای انتخاب پوشهٔ والت در تنظیمات، و همان‌جا ذخیره می‌شود.
    """
    conn = get_db()
    kind = body().get("kind", "file")
    if kind == "folder":
        # برای پوشهٔ خروجی و backup در تنظیمات: فقط آدرس برمی‌گردد، ذخیره با دکمهٔ «ذخیره»
        path = sources.browse("folder", _("یک پوشه انتخاب کنید"))
        return jsonify({"cancelled": True} if path is None else {"path": path})
    if kind == "vault":
        path = sources.browse("folder", _("پوشهٔ والت Obsidian را انتخاب کنید"))
        if path is None:
            return jsonify({"cancelled": True})
        database.set_setting(conn, "vault_path", path)
        return state_response()
    path = sources.browse("file", _("فایل منبع را انتخاب کنید"))
    if path is None:
        return jsonify({"cancelled": True})
    source_type, stored = sources.classify_path(path, database.get_settings(conn)["vault_path"])
    return jsonify({"source_type": source_type, "source_path_or_url": stored, "outline": sources.file_outline(path)})


@bp.route("/api/categories", methods=["POST"])
def api_add_category():
    name = str(body().get("name", "")).strip()
    if not name:
        raise UserError(_("نام دسته خالی است."))
    database.add_category(get_db(), name)
    return state_response()


@bp.route("/api/categories/<int:category_id>", methods=["PATCH"])
def api_rename_category(category_id):
    name = str(body().get("name", "")).strip()
    if not name:
        raise UserError(_("نام دسته خالی است."))
    database.rename_category(get_db(), category_id, name)
    return state_response()


@bp.route("/api/categories/<int:category_id>", methods=["DELETE"])
def api_delete_category(category_id):
    database.delete_category(get_db(), category_id)
    return state_response()


@bp.route("/api/categories/reorder", methods=["POST"])
def api_reorder_categories():
    conn = get_db()
    ids = body().get("ids")
    existing = {c["id"] for c in database.list_categories(conn)}
    if not isinstance(ids, list) or set(ids) != existing:
        raise UserError(_("ترتیب دسته‌ها نامعتبر است."))
    database.reorder_categories(conn, ids)
    return state_response()


@bp.route("/api/settings", methods=["PATCH"])
def api_settings():
    """چند تنظیم را با هم ذخیره می‌کند. هر مقدار اول بررسی می‌شود؛ اگر یکی نامعتبر بود، هیچ‌کدام ذخیره نمی‌شود."""
    conn = get_db()
    cleaned = {}
    for key, value in body().items():
        try:
            cleaned[key] = database.clean_setting(key, value)
        except ValueError as error:
            raise UserError(str(error))
    for key, value in cleaned.items():
        database.set_setting(conn, key, value)
    return state_response()


@bp.route("/api/fonts/add", methods=["POST"])
def api_add_font():
    """یک فایل فونت را با Browse انتخاب می‌کند و کپی‌اش را در data/fonts می‌گذارد."""
    chosen = sources.browse("file", _("فایل فونت را انتخاب کنید (ttf، otf، woff یا woff2)"))
    if chosen is None:
        return jsonify({"cancelled": True})
    family = data_service.add_font(get_db(), chosen)
    state = build_state()
    state["added_font"] = family
    return jsonify(state)


@bp.route("/api/fonts/remove", methods=["POST"])
def api_remove_font():
    conn = get_db()
    family = body().get("family")
    settings = database.get_settings(conn)
    fonts = [f for f in settings["custom_fonts"] if f["family"] != family]
    database.set_setting(conn, "custom_fonts", fonts)
    if settings["font_family"] == family:
        database.set_setting(conn, "font_family", "Vazirmatn")
    return state_response()


@bp.route("/fonts/<name>")
def serve_font(name):
    """فایل فونت‌های اضافه‌شده، فقط از پوشهٔ data/fonts."""
    path = database.FONTS_DIR / Path(name).name
    if path.suffix.lower() not in data_service.FONT_SUFFIXES or not path.is_file():
        abort(404)
    return send_file(path, mimetype=data_service.FONT_SUFFIXES[path.suffix.lower()])


def _type_fields(data):
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 40:
        raise UserError(_("نام نوع کار باید بین 1 تا 40 حرف باشد."))
    try:
        color = database.clean_color(data.get("color", "#8b5cf6"))
    except ValueError as error:
        raise UserError(str(error))
    return name, color


@bp.route("/api/types", methods=["POST"])
def api_add_type():
    data = body()
    name, color = _type_fields(data)
    behavior = data.get("behavior", "study")
    if behavior not in ("study", "routine"):
        raise UserError(_("رفتار نوع کار نامعتبر است."))
    database.add_type(get_db(), name, behavior, color)
    return state_response()


@bp.route("/api/types/<int:type_id>", methods=["PATCH"])
def api_update_type(type_id):
    if database.get_type(get_db(), type_id) is None:
        abort(404)
    name, color = _type_fields(body())
    database.update_type(get_db(), type_id, name, color)
    return state_response()


@bp.route("/api/types/<int:type_id>", methods=["DELETE"])
def api_delete_type(type_id):
    database.delete_type(get_db(), type_id)
    return state_response()
