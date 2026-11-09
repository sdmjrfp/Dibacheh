"""backup، انتقال داده‌ها و فونت‌های اضافه‌شده."""

import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import database
import sources
from errors import UserError

FONT_SUFFIXES = {".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2"}


def restore_backup(conn, folder, name, safety_folder=None):
    """یک backup را برمی‌گرداند. قبلش یک کپی جدا از وضعیت فعلی گرفته می‌شود."""
    if name not in {b["name"] for b in database.list_backups(folder)}:
        raise UserError("این backup پیدا نشد.")
    try:
        database.check_database_file(folder / name)
    except ValueError as error:
        raise UserError(str(error))
    database.safety_copy(conn, safety_folder or folder, datetime.now())
    database.replace_database(conn, folder / name)


def export_data(conn, folder, day):
    """همهٔ داده‌ها در یک فایل zip: دیتابیس و فونت‌های اضافه‌شده."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"dibacheh-data-{day.isoformat()}.zip"
    with tempfile.TemporaryDirectory() as work:
        copy = Path(work) / "dibacheh.sqlite3"
        target = sqlite3.connect(copy)
        try:
            conn.backup(target)
        finally:
            target.close()
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(copy, "dibacheh.sqlite3")
            if database.FONTS_DIR.is_dir():
                for font in database.FONTS_DIR.iterdir():
                    if font.suffix.lower() in FONT_SUFFIXES:
                        archive.write(font, f"fonts/{font.name}")
    return path


def import_data(conn, chosen, backups):
    """فایل zip داده‌ها را با Browse می‌گیرد و جای داده‌های فعلی می‌گذارد."""
    try:
        with zipfile.ZipFile(chosen) as archive, tempfile.TemporaryDirectory() as work:
            if "dibacheh.sqlite3" not in archive.namelist():
                raise UserError("این فایل دادهٔ دیباچه ندارد.")
            copy = Path(work) / "incoming.sqlite3"
            copy.write_bytes(archive.read("dibacheh.sqlite3"))
            try:
                database.check_database_file(copy)
            except ValueError as error:
                raise UserError(str(error))
            database.safety_copy(conn, backups, datetime.now())
            database.replace_database(conn, copy)
            # فقط نام فایل استفاده می‌شود، پس فایل zip نمی‌تواند بیرون از پوشهٔ فونت‌ها چیزی بنویسد
            database.FONTS_DIR.mkdir(parents=True, exist_ok=True)
            for name in archive.namelist():
                if name.startswith("fonts/") and Path(name).suffix.lower() in FONT_SUFFIXES:
                    (database.FONTS_DIR / Path(name).name).write_bytes(archive.read(name))
    except zipfile.BadZipFile:
        raise UserError("این فایل zip معتبر نیست.")


def add_font(conn, chosen):
    """یک فایل فونت را با Browse انتخاب می‌کند و کپی‌اش را در data/fonts می‌گذارد."""
    source = Path(chosen)
    if source.suffix.lower() not in FONT_SUFFIXES:
        raise UserError("این فایل فونت نیست. فقط ttf، otf، woff و woff2.")
    try:
        family = sources.font_family_name(source)
        family = database.clean_setting("font_family", family)
    except Exception:
        raise UserError("نام این فونت خوانده نشد.")
    database.FONTS_DIR.mkdir(parents=True, exist_ok=True)
    target = database.FONTS_DIR / source.name
    target.write_bytes(source.read_bytes())
    fonts = [f for f in database.get_settings(conn)["custom_fonts"] if f["family"] != family]
    fonts.append({"family": family, "file": target.name})
    database.set_setting(conn, "custom_fonts", fonts)
    return family
