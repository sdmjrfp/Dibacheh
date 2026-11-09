"""مسیرهای خروجی، گزارش، backup و انتقال داده‌ها."""

from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

import config
import database
import exporter
import platform_tools
import reports
import sources
from errors import UserError
from i18n import _
from services import data as data_service
from webutil import body, get_db, json_ready, parse_date, state_data, state_response, today

bp = Blueprint("data", __name__)


def export_folder():
    return Path(database.get_settings(get_db())["export_folder"] or "~/Documents/Dibacheh Exports").expanduser()


def export_file(name):
    """فقط فایلی که خود برنامه در پوشهٔ خروجی ساخته؛ نه هر آدرس دلخواه."""
    if (not isinstance(name, str) or "/" in name or "\\" in name or name.startswith(".")
            or not name.endswith((".html", ".zip"))):
        raise UserError(_("نام فایل نامعتبر است."))
    path = export_folder() / name
    if not path.is_file():
        raise UserError(_("فایل خروجی پیدا نشد."))
    return path


@bp.route("/api/export", methods=["POST"])
def api_export():
    """خروجی روز، هفته یا ماه را می‌سازد و در پوشهٔ خروجی ذخیره می‌کند."""
    data = body()
    scope = data.get("scope", "day")
    if scope not in ("day", "week", "month"):
        raise UserError(_("نوع خروجی نامعتبر است."))
    day = parse_date(data.get("date")) or today()
    # خروجی روزانه به‌طور پیش‌فرض مطالب را هم دارد؛ هفتگی و ماهانه فقط فهرست کارها
    with_content = bool(data.get("with_content", scope == "day"))
    state = state_data()
    path = exporter.export(state, scope, day, with_content,
                           state["settings"]["vault_path"], export_folder())
    return jsonify({"name": path.name, "path": str(path), "size": path.stat().st_size})


@bp.route("/api/export/file/<path:name>")
def apiexport_file(name):
    """فایل خروجی را به مرورگر می‌دهد (برای پنجرهٔ Share)."""
    return send_file(export_file(name), mimetype="text/html", as_attachment=True, download_name=name)


@bp.route("/api/export/reveal", methods=["POST"])
def api_export_reveal():
    """فایل را در Finder انتخاب‌شده نشان می‌دهد تا بشود آن را به تلگرام یا هر برنامه‌ای کشید."""
    platform_tools.launch(platform_tools.reveal_args(export_file(body().get("name"))))
    return jsonify({"ok": True})


@bp.route("/api/export/open", methods=["POST"])
def api_export_open():
    platform_tools.launch(platform_tools.open_args(export_file(body().get("name"))))
    return jsonify({"ok": True})


def _period(value):
    if value in (None, ""):
        return "week"
    if value not in ("week", "month", "all"):
        raise UserError(_("بازهٔ گزارش نامعتبر است."))
    return value


@bp.route("/api/stats")
def api_stats():
    state = state_data()
    data = reports.stats(get_db(), state["items"], state["categories"], state["today"])
    data["summary"] = reports.summary(get_db(), state, _period(request.args.get("period")),
                                      parse_date(request.args.get("date")) or state["today"])
    return jsonify(json_ready(data))


@bp.route("/api/export/report", methods=["POST"])
def api_export_report():
    """گزارش هفتگی، ماهانه یا کلی به شکل فایل HTML، در پوشهٔ خروجی."""
    state = state_data()
    data = body()
    report = reports.summary(get_db(), state, _period(data.get("period")),
                             parse_date(data.get("date")) or state["today"])
    path = exporter.export_report(report, state, export_folder())
    return jsonify({"name": path.name, "path": str(path), "size": path.stat().st_size})


@bp.route("/api/backups")
def api_backups():
    folder = config.backups_dir(database.get_settings(get_db()))
    return jsonify(json_ready(database.list_backups(folder)))


@bp.route("/api/backups/restore", methods=["POST"])
def api_restore_backup():
    """یک backup را برمی‌گرداند. قبلش یک کپی جدا از وضعیت فعلی گرفته می‌شود."""
    conn = get_db()
    data = body()
    settings = database.get_settings(conn)
    folder = cloud_backups(settings) if data.get("cloud") else config.backups_dir(settings)
    data_service.restore_backup(conn, folder, data.get("name"), safety_folder=config.backups_dir(settings))
    return state_response()


def cloud_backups(settings):
    if not settings["cloud_backup_folder"]:
        raise UserError(_("پوشهٔ ابری انتخاب نشده است."))
    return Path(settings["cloud_backup_folder"]).expanduser() / database.CLOUD_SUBFOLDER


@bp.route("/api/backups/cloud")
def api_cloud_backups():
    """پوشه‌های ابری پیداشده، و نسخه‌هایی که در پوشهٔ انتخاب‌شده هست."""
    settings = database.get_settings(get_db())
    copies = []
    if settings["cloud_backup_folder"]:
        folder = cloud_backups(settings)
        copies = database.list_backups(folder) if folder.is_dir() else []
    return jsonify(json_ready({"folders": platform_tools.cloud_folders(), "selected": settings["cloud_backup_folder"], "copies": copies}))


@bp.route("/api/backups/cloud/now", methods=["POST"])
def api_cloud_backup_now():
    settings = database.get_settings(get_db())
    if not settings["cloud_backup_folder"]:
        raise UserError(_("پوشهٔ ابری انتخاب نشده است."))
    try:
        path = database.copy_backup_to_cloud(config.backups_dir(settings), settings["cloud_backup_folder"], settings["backup_retention"])
    except OSError as error:
        raise UserError(_("کپی نشد: {0}", error))
    return jsonify({"copied": bool(path)})


@bp.route("/api/data/export", methods=["POST"])
def api_export_data():
    """همهٔ داده‌ها در یک فایل zip: دیتابیس و فونت‌های اضافه‌شده."""
    path = data_service.export_data(get_db(), export_folder(), today())
    return jsonify({"name": path.name, "path": str(path), "size": path.stat().st_size})


@bp.route("/api/data/import", methods=["POST"])
def api_import_data():
    """فایل zip داده‌ها را با Browse می‌گیرد و جای داده‌های فعلی می‌گذارد."""
    chosen = sources.browse("file", _("فایل داده‌های دیباچه را انتخاب کنید (zip)"))
    if chosen is None:
        return jsonify({"cancelled": True})
    conn = get_db()
    data_service.import_data(conn, chosen, config.backups_dir(database.get_settings(conn)))
    return state_response()
