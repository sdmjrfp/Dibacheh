"""تنظیم‌های ثابت اجرای برنامه: آدرس سرور، پورت، توکن امنیتی و مسیرها."""

import logging
import os
import secrets
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import database
import platform_tools

# آدرس و پورت سرور.
# 127.0.0.1 یعنی فقط خود همین کامپیوتر می‌تواند به برنامه وصل شود،
# نه گوشی یا کامپیوتر دیگری در شبکه.
HOST = "127.0.0.1"
# پورت را می‌شود برای امتحان عوض کرد: DIBACHEH_PORT=5001 .venv/bin/python app.py
# نسخهٔ نصبی پورت دیگری دارد، چون AirPlay Receiver روی خیلی از Macها پورت 5000 را گرفته است.
FROZEN = platform_tools.is_frozen()
PORT = int(os.environ.get("DIBACHEH_PORT") or (5847 if FROZEN else 5000))
# نسخهٔ نصبی ویندوز و لینوکس آیکون Dock ندارد، پس دکمهٔ «بستن برنامه» در صفحه می‌آید
CAN_QUIT = FROZEN and platform_tools.system() != "mac"
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

# توکن CSRF: هر بار که برنامه اجرا می‌شود یک رمز تصادفی تازه ساخته می‌شود.
# فقط صفحهٔ خود برنامه آن را می‌داند و همراه هر تغییر می‌فرستد.
# سایت‌های دیگری که در مرورگر باز هستند این رمز را ندارند، پس نمی‌توانند چیزی را تغییر دهند.
CSRF_TOKEN = secrets.token_urlsafe(32)

# فایل‌های صفحه: کنار همین فایل، یا در نسخهٔ نصبی داخل بستهٔ برنامه
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _read_version():
    try:
        return (RESOURCE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


VERSION = _read_version()


def backups_dir(settings):
    """پوشهٔ backup. نسخهٔ آزمایشی با دیتابیس جدا، backup خودش را کنار همان دیتابیس می‌گذارد
    تا در backupهای اصلی قاطی نشود."""
    if os.environ.get("DIBACHEH_DB"):
        return Path(os.environ["DIBACHEH_DB"]).parent / "backups-test"
    return database.backup_folder(settings)


def log_file():
    """فایل گزارش خطا. نسخهٔ آزمایشی با دیتابیس جدا، گزارش خودش را کنار همان فایل می‌گذارد."""
    if os.environ.get("DIBACHEH_DB"):
        return Path(os.environ["DIBACHEH_DB"]).parent / "logs" / "dibacheh.log"
    return database.DATA_DIR / "logs" / "dibacheh.log"


def setup_logging():
    """گزارش خطا در یک فایل با حجم محدود: 3 فایل، هر کدام حداکثر نیم مگابایت."""
    path = log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=500_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.WARNING)
