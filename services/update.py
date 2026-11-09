"""بررسی نسخهٔ تازه در GitHub و دانلود فایل نصب.

این تنها جایی است که خود برنامه به اینترنت وصل می‌شود. بررسی در پس‌زمینه است و اگر
اینترنت قطع بود یا GitHub جواب نداد، بی‌سروصدا هیچ اتفاقی نمی‌افتد و برنامه منتظر نمی‌ماند.
فایل فقط دانلود می‌شود؛ نصب را خود کاربر انجام می‌دهد.
"""

import json
import logging
import platform
import re
import ssl
import threading
import urllib.request
from pathlib import Path

import platform_tools
from errors import UserError

LATEST_URL = "https://api.github.com/repos/sdmjrfp/Dibacheh/releases/latest"
DOWNLOAD_PREFIX = "https://github.com/sdmjrfp/Dibacheh/releases/download/"
CHECK_TIMEOUT = 8

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_cached = None    # نتیجهٔ بررسی؛ در هر بار اجرای برنامه یک بار از GitHub خوانده می‌شود
progress = {"state": "idle", "received": 0, "total": 0, "path": None, "error": None}


def _ssl_context():
    """گواهی‌های امنیتی همراه برنامه، چون نسخهٔ نصبی به گواهی‌های سیستم دسترسی مطمئن ندارد."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def parse_version(text):
    """«v1.2.0» → (1, 2, 0). متن نامعتبر → None."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(latest, current):
    latest, current = parse_version(latest), parse_version(current)
    return bool(latest and current and latest > current)


def asset_suffix(system, machine):
    """فایل نصب مناسب این کامپیوتر."""
    if system == "mac":
        return "-AppleSilicon.dmg" if machine == "arm64" else "-Intel.dmg"
    if system == "windows":
        return "-Windows-Setup.exe"
    return "-Linux-x86_64.AppImage"


def notes_for(body, language):
    """متن تغییرات به زبان کاربر. متن Release می‌تواند با <!-- lang:en --> بخش‌بندی شده باشد."""
    parts = re.split(r"<!--\s*lang:([\w-]+)\s*-->", body or "")
    if len(parts) == 1:
        return (body or "").strip()
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    return sections.get(language) or sections.get("en") or next(iter(sections.values()))


def read_release(data, current, language, system, machine):
    """جواب GitHub را به آنچه صفحه لازم دارد تبدیل می‌کند."""
    latest = str(data.get("tag_name", "")).lstrip("v")
    if data.get("draft") or data.get("prerelease") or not is_newer(latest, current):
        return {"available": False, "latest": latest}
    suffix = asset_suffix(system, machine)
    asset = next((a for a in data.get("assets", []) if str(a.get("name", "")).endswith(suffix)), None)
    if asset is None or not str(asset.get("browser_download_url", "")).startswith(DOWNLOAD_PREFIX):
        return {"available": False, "latest": latest}
    return {
        "available": True,
        "latest": latest,
        "notes": notes_for(data.get("body"), language),
        "asset": {"name": Path(asset["name"]).name, "url": asset["browser_download_url"], "size": asset.get("size", 0)},
    }


def check(current, language, fetch=None):
    """آیا نسخهٔ تازه‌ای آمده؟ هیچ خطایی از این تابع بیرون نمی‌آید."""
    global _cached
    with _lock:
        if _cached is None:
            try:
                request = urllib.request.Request(LATEST_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "Dibacheh"})
                if fetch:
                    _cached = fetch()
                else:
                    with urllib.request.urlopen(request, timeout=CHECK_TIMEOUT, context=_ssl_context()) as response:
                        _cached = json.load(response)
            except (OSError, ValueError) as error:   # اینترنت قطع، GitHub در دسترس نیست، جواب خراب
                _log.info("بررسی نسخهٔ تازه انجام نشد: %s", error)
                return {"available": False, "failed": True}
    return read_release(_cached, current, language, platform_tools.system(), platform.machine())


def reset():
    """برای تست."""
    global _cached
    _cached = None
    progress.update(state="idle", received=0, total=0, path=None, error=None)


def downloads_folder():
    return Path.home() / "Downloads"


def _download(url, target, size):
    part = target.with_name(target.name + ".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Dibacheh"})
        with urllib.request.urlopen(request, timeout=60, context=_ssl_context()) as response, part.open("wb") as out:
            while chunk := response.read(256 * 1024):
                out.write(chunk)
                progress["received"] += len(chunk)
        # فایل ناقص نباید با نام نهایی بماند
        if size and part.stat().st_size != size:
            raise OSError("حجم فایل دانلودشده درست نیست.")
        part.replace(target)
        progress.update(state="done", path=str(target))
    except OSError as error:
        _log.warning("دانلود نسخهٔ تازه نشد: %s", error)
        part.unlink(missing_ok=True)
        progress.update(state="failed", error=str(error))


def start_download(asset, folder=None):
    """دانلود را در پس‌زمینه شروع می‌کند. پیشرفت در progress است."""
    url = str(asset.get("url", ""))
    if not url.startswith(DOWNLOAD_PREFIX):
        raise UserError("آدرس دانلود نامعتبر است.")
    if progress["state"] == "downloading":
        return
    folder = Path(folder) if folder else downloads_folder()
    folder.mkdir(parents=True, exist_ok=True)
    progress.update(state="downloading", received=0, total=asset.get("size", 0), path=None, error=None)
    threading.Thread(target=_download, args=(url, folder / Path(asset["name"]).name, asset.get("size", 0)), daemon=True).start()
