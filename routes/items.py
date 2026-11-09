"""مسیرهای درس‌ها و جلسه‌ها."""

from flask import Blueprint, jsonify

import database
import sources
from errors import UserError
from services import items as item_service
from services.items import require_item
from webutil import body, build_state, get_db, state_response, today

bp = Blueprint("items", __name__)


@bp.route("/api/items", methods=["POST"])
def api_add_item():
    item_service.create_item(get_db(), body(), today())
    return state_response()


@bp.route("/api/items/<int:item_id>", methods=["PATCH"])
def api_update_item(item_id):
    item_service.update_item(get_db(), item_id, body())
    return state_response()


@bp.route("/api/items/<int:item_id>/split", methods=["POST"])
def api_split_item(item_id):
    item_service.split_item(get_db(), item_id, body())
    return state_response()


@bp.route("/api/items/<int:item_id>/archive", methods=["POST"])
def api_archive_item(item_id):
    item_service.archive_item(get_db(), item_id, bool(body().get("archived", True)))
    return state_response()


@bp.route("/api/items/bulk", methods=["POST"])
def api_bulk_add():
    item_service.bulk_add(get_db(), body())
    return state_response()


@bp.route("/api/items/reorder", methods=["POST"])
def api_reorder():
    released = item_service.reorder(get_db(), body())
    state = build_state()
    state["released"] = released
    return jsonify(state)


@bp.route("/api/sessions/<int:session_id>", methods=["PATCH"])
def api_update_session(session_id):
    item_service.update_session(get_db(), session_id, body())
    return state_response()


@bp.route("/api/items/<int:item_id>/outline")
def api_item_outline(item_id):
    """ساختار فایل منبع یک درس ثبت‌شده، برای ساختن جلسه‌ها از عنوان‌ها یا فصل‌ها."""
    conn = get_db()
    item = require_item(conn, item_id)
    location = sources.source_location(item, database.get_settings(conn)["vault_path"])
    return jsonify({"outline": sources.file_outline(location) if location else None})


@bp.route("/api/items/<int:item_id>", methods=["DELETE"])
def api_delete_item(item_id):
    """درس، جلسه‌ها و سابقه‌اش پاک می‌شود. فایل منبع روی کامپیوتر دست نمی‌خورد."""
    database.delete_item(get_db(), item_id)
    return state_response()


@bp.route("/api/items/<int:item_id>/reset", methods=["POST"])
def api_reset_item(item_id):
    database.reset_item(get_db(), item_id)
    return state_response()


@bp.route("/api/items/<int:item_id>/reviews", methods=["DELETE"])
def api_remove_reviews(item_id):
    item_service.remove_reviews(get_db(), item_id)
    return state_response()


@bp.route("/api/items/<int:item_id>/reviews", methods=["POST"])
def api_restore_reviews(item_id):
    item_service.restore_reviews(get_db(), item_id)
    return state_response()


@bp.route("/api/items/<int:item_id>/unpin", methods=["POST"])
def api_unpin_item(item_id):
    """همهٔ جابه‌جایی‌های دستی یک درس (خواندن و مرور) برداشته می‌شود و برمی‌گردد به چینش خودکار."""
    database.clear_manual_dates(get_db(), item_id)
    return state_response()


@bp.route("/api/items/<int:item_id>/open", methods=["POST"])
def api_open_source(item_id):
    """منبع ثبت‌شدهٔ یک درس را باز می‌کند. آدرس از دیتابیس می‌آید، نه از مرورگر."""
    conn = get_db()
    item = require_item(conn, item_id)
    problem = sources.open_source(item, database.get_settings(conn)["vault_path"])
    if problem:
        raise UserError(problem)
    return jsonify({"ok": True})


@bp.route("/api/items/<int:item_id>/headings")
def api_headings(item_id):
    conn = get_db()
    item = require_item(conn, item_id)
    return jsonify(sources.markdown_headings(item, database.get_settings(conn)["vault_path"]))
