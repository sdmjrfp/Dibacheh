"""کاربران برنامه روی یک کامپیوتر.

هر پروفایل دیتابیس، backup، فونت و پوشهٔ خروجی خودش را دارد. فهرست پروفایل‌ها و رمزها در
profiles.json است، بیرون از دیتابیس. برای همین هیچ backupی رمز ندارد و کسی که رمزش را
فراموش کرده، با یک کاربر تازه و برگرداندن backup کارش را ادامه می‌دهد.

رمز برای جدا نگه داشتن کاربران یک کامپیوتر است، نه حفاظت جدی: دیتابیس‌ها رمزنگاری نشده‌اند.

پروفایل اول همان داده‌های قبلی است و جابه‌جا نمی‌شود (پوشهٔ data). پروفایل‌های بعدی در
data/profiles/<نام>-<شناسه> هستند. برنامه یک نفره است، پس کاربر فعلی متغیر همین برنامه است
و عوض کردنش به اجرای دوبارهٔ برنامه نیاز ندارد.
"""

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path

import database
from errors import UserError
from i18n import _

MAIN_ID = "main"
AVATAR = re.compile(r"a([1-9]|1[0-2])")
PHOTO_NAME = "profile-photo.jpg"
PHOTO_LIMIT = 3_000_000
PBKDF2_ROUNDS = 100_000

_active = {}      # ریشهٔ داده → شناسهٔ کاربری که وارد شده است
_last = {}        # ریشهٔ داده → آخرین کاربر، برای زبان صفحهٔ ورود
_originals = {}   # مسیرهای پیش‌فرض پروفایل اول


def _root(main_db):
    return Path(main_db).parent


def _file(main_db):
    return _root(main_db) / "profiles.json"


def load(main_db):
    path = _file(main_db)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"profiles": [{"id": MAIN_ID, "name": _("کاربر ۱"), "folder": "", "avatar": "a1", "has_photo": False, "salt": "", "hash": ""}]}


def _save(main_db, data):
    path = _file(main_db)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _find(data, profile_id):
    for profile in data["profiles"]:
        if profile["id"] == profile_id:
            return profile
    raise UserError(_("این کاربر پیدا نشد."))


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()


def _set_password(profile, password):
    if password:
        profile["salt"] = secrets.token_hex(16)
        profile["hash"] = _hash(password, profile["salt"])
    else:
        profile["salt"] = profile["hash"] = ""


def folder_of(main_db, profile):
    return _root(main_db) / profile["folder"] if profile["folder"] else _root(main_db)


def db_of(main_db, profile):
    return Path(main_db) if profile["id"] == MAIN_ID else folder_of(main_db, profile) / "dibacheh.sqlite3"


def current(main_db):
    """کاربر فعلی. اگر فقط یک کاربر بدون رمز باشد، بدون پرسش وارد می‌شود. None یعنی صفحهٔ ورود."""
    key = str(main_db)
    data = load(main_db)
    known = {p["id"]: p for p in data["profiles"]}
    if key in _active and _active[key] in known:
        return known[_active[key]]
    if len(known) == 1:
        only = data["profiles"][0]
        if not only["hash"]:
            _activate(main_db, only)
            return only
    return None


def page_profile(main_db):
    """پروفایلی که زبان و تقویم صفحهٔ ورود از آن می‌آید."""
    data = load(main_db)
    known = {p["id"]: p for p in data["profiles"]}
    return known.get(_last.get(str(main_db))) or known.get(data.get("last")) or data["profiles"][0]


def current_db(main_db):
    active = current(main_db)
    return db_of(main_db, active or page_profile(main_db))


def _activate(main_db, profile):
    """مسیرهای مشترک برنامه را روی این کاربر می‌گذارد."""
    _active[str(main_db)] = profile["id"]
    _last[str(main_db)] = profile["id"]
    if not _originals:
        _originals.update(fonts=database.FONTS_DIR, cloud=database.CLOUD_SUBFOLDER)
    if profile["id"] == MAIN_ID:
        database.FONTS_DIR = _originals["fonts"]
        database.CLOUD_SUBFOLDER = _originals["cloud"]
    else:
        database.FONTS_DIR = folder_of(main_db, profile) / "fonts"
        database.CLOUD_SUBFOLDER = f"{_originals['cloud']} - {profile['folder'].rsplit('/', 1)[-1]}"


def reset():
    """برای تست: برگشت به حالت شروع برنامه."""
    if _originals:
        database.FONTS_DIR = _originals["fonts"]
        database.CLOUD_SUBFOLDER = _originals["cloud"]
    _active.clear()
    _last.clear()
    _originals.clear()


def public(main_db):
    """آنچه صفحه می‌بیند؛ بدون رمز."""
    data = load(main_db)
    active = current(main_db)
    return {
        "active": active["id"] if active else None,
        "login_required": active is None,
        "profiles": [{"id": p["id"], "name": p["name"], "avatar": p["avatar"], "has_photo": p["has_photo"],
                      "has_password": bool(p["hash"]), "is_main": p["id"] == MAIN_ID} for p in data["profiles"]],
    }


def login(main_db, profile_id, password=""):
    data = load(main_db)
    profile = _find(data, profile_id)
    if profile["hash"] and not hmac.compare_digest(_hash(str(password or ""), profile["salt"]), profile["hash"]):
        raise UserError(_("رمز درست نیست."))
    _activate(main_db, profile)
    data["last"] = profile["id"]
    _save(main_db, data)


def _clean_name(data, name, own_id=None):
    name = str(name or "").strip()
    if not 1 <= len(name) <= 40:
        raise UserError(_("نام کاربر باید بین 1 تا 40 حرف باشد."))
    if any(p["name"].casefold() == name.casefold() and p["id"] != own_id for p in data["profiles"]):
        raise UserError(_("کاربری با این نام هست."))
    return name


def _clean_avatar(avatar):
    if not AVATAR.fullmatch(str(avatar or "")):
        raise UserError(_("تصویر انتخاب‌شده نامعتبر است."))
    return avatar


def safe_name(name):
    """نام برای پوشه؛ حرف‌های فارسی می‌مانند و فقط نشانه‌های خطرناک حذف می‌شوند."""
    return re.sub(r"[^\w\- ]+", "", name).strip().replace(" ", "-")[:30] or "user"


def own_paths(profile):
    """پوشهٔ backup و خروجی این کاربر، تا فایل‌ها قاطی نشوند."""
    label = safe_name(profile["name"])
    return {"backup_folder": str(Path(profile["_folder"]) / "backups"), "export_folder": f"~/Documents/Dibacheh Exports/{label}"}


def create(main_db, name, avatar, password, from_settings):
    """کاربر تازه با دیتابیس خالی. زبان و تقویم از کاربر فعلی می‌آید تا دوباره پرسیده نشود."""
    data = load(main_db)
    name = _clean_name(data, name)
    profile = {"id": secrets.token_hex(3), "name": name, "avatar": _clean_avatar(avatar), "has_photo": False, "salt": "", "hash": ""}
    profile["folder"] = f"profiles/{safe_name(name)}-{profile['id']}"
    _set_password(profile, password)
    folder = folder_of(main_db, profile)
    folder.mkdir(parents=True, exist_ok=True)
    conn = database.connect(db_of(main_db, profile))
    try:
        values = {key: from_settings[key] for key in ("language", "calendar", "first_weekday", "font_family", "theme")}
        values.update(own_paths({**profile, "_folder": str(folder)}), setup_done=True)
        for key, value in values.items():
            database.set_setting(conn, key, value)
        conn.commit()
    finally:
        conn.close()
    data["profiles"].append(profile)
    _save(main_db, data)
    return profile["id"]


def update(main_db, profile_id, fields):
    data = load(main_db)
    profile = _find(data, profile_id)
    if "name" in fields:
        profile["name"] = _clean_name(data, fields["name"], profile_id)
    if "avatar" in fields:
        profile["avatar"] = _clean_avatar(fields["avatar"])
    if "password" in fields:
        _set_password(profile, str(fields["password"] or ""))
    if fields.get("remove_photo"):
        (folder_of(main_db, profile) / PHOTO_NAME).unlink(missing_ok=True)
        profile["has_photo"] = False
    if fields.get("photo"):
        _save_photo(main_db, profile, fields["photo"])
    _save(main_db, data)


def _save_photo(main_db, profile, data_url):
    """عکس را صفحه کوچک کرده و به شکل JPEG می‌فرستد."""
    try:
        raw = base64.b64decode(str(data_url).split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise UserError(_("این فایل عکس نیست."))
    if len(raw) > PHOTO_LIMIT or not raw.startswith(b"\xff\xd8"):
        raise UserError(_("این فایل عکس نیست."))
    folder = folder_of(main_db, profile)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / PHOTO_NAME).write_bytes(raw)
    profile["has_photo"] = True


def photo_path(main_db, profile_id):
    profile = _find(load(main_db), profile_id)
    path = folder_of(main_db, profile) / PHOTO_NAME
    return path if profile["has_photo"] and path.is_file() else None


def delete(main_db, profile_id):
    """کاربر پاک نمی‌شود، بلکه به پوشهٔ profiles-deleted می‌رود تا داده‌اش از دست نرود."""
    data = load(main_db)
    profile = _find(data, profile_id)
    if profile["id"] == MAIN_ID:
        raise UserError(_("کاربر اصلی حذف نمی‌شود."))
    target = _root(main_db) / "profiles-deleted" / f"{Path(profile['folder']).name}-{datetime.now():%Y%m%d-%H%M%S}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(folder_of(main_db, profile)), str(target))
    data["profiles"] = [p for p in data["profiles"] if p["id"] != profile_id]
    data.pop("last", None)
    _save(main_db, data)
    _active.pop(str(main_db), None)
    _last.pop(str(main_db), None)
    if _originals:
        database.FONTS_DIR = _originals["fonts"]
        database.CLOUD_SUBFOLDER = _originals["cloud"]


def fix_paths_after_import(conn, main_db, profile):
    """backup کاربر دیگر مسیرهای او را هم دارد؛ بعد از ورود، مسیرها مال کاربر فعلی می‌شوند."""
    if profile["id"] != MAIN_ID:
        values = own_paths({**profile, "_folder": str(folder_of(main_db, profile))})
    else:
        settings = database.get_settings(conn)
        values = {}
        if "/profiles/" in str(settings["backup_folder"]).replace("\\", "/"):
            values["backup_folder"] = database.DEFAULT_SETTINGS["backup_folder"]
        if "Dibacheh Exports/" in str(settings["export_folder"]):
            values["export_folder"] = database.DEFAULT_SETTINGS["export_folder"]
    for key, value in values.items():
        database.set_setting(conn, key, value)
