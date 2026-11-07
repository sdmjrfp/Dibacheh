"""هر چیزی که بین macOS، ویندوز و لینوکس فرق دارد، همین‌جاست.

  app_home()     پوشهٔ داده‌ها
  open_args()    دستور باز کردن فایل یا لینک با برنامهٔ پیش‌فرض
  reveal_args()  دستور نشان دادن فایل در مدیر فایل
  choose()       پنجرهٔ انتخاب فایل یا پوشهٔ خود سیستم

همهٔ دستورها فهرست آرگومان‌اند و بدون shell اجرا می‌شوند،
تا نام فایل‌های عجیب نتوانند دستور اضافه اجرا کنند.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


class BrowseUnavailable(Exception):
    """پنجرهٔ انتخاب فایل روی این سیستم در دسترس نیست."""


def system():
    if sys.platform == "darwin":
        return "mac"
    return "windows" if sys.platform.startswith("win") else "linux"


def is_frozen():
    """آیا این نسخهٔ نصبی است (نه اجرا از سورس)؟"""
    return getattr(sys, "frozen", False)


def app_home():
    """پوشه‌ای که داده‌ها در آن است.

    اجرا از سورس: پوشهٔ پروژه. نسخهٔ نصبی: پوشهٔ دادهٔ کاربر، تا با به‌روزرسانی یا حذف
    برنامه داده‌ها از بین نرود. DIBACHEH_HOME برای تست نسخهٔ نصبی است.
    """
    if os.environ.get("DIBACHEH_HOME"):
        return Path(os.environ["DIBACHEH_HOME"])
    if not is_frozen():
        return Path(__file__).resolve().parent
    if system() == "mac":
        return Path.home() / "Library" / "Application Support" / "Dibacheh"
    if system() == "windows":
        return Path(os.environ.get("APPDATA") or Path.home()) / "Dibacheh"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "dibacheh"


def open_args(target):
    """دستور باز کردن یک فایل یا لینک (obsidian:// هم) با برنامهٔ پیش‌فرض."""
    if system() == "mac":
        return ["open", str(target)]
    if system() == "windows":
        return ["rundll32", "url.dll,FileProtocolHandler", str(target)]
    return ["xdg-open", str(target)]


def reveal_args(path):
    """دستور نشان دادن یک فایل در مدیر فایل."""
    if system() == "mac":
        return ["open", "-R", str(path)]
    if system() == "windows":
        return ["explorer", f"/select,{path}"]
    return ["xdg-open", str(Path(path).parent)]   # لینوکس راه مشترکی برای انتخاب فایل ندارد


def run_env():
    """محیط اجرای برنامه‌های دیگر.

    نسخهٔ نصبی لینوکس مسیر کتابخانه‌های خودش را تنظیم می‌کند. اگر همان به مرورگر برسد،
    مرورگر باز نمی‌شود، پس مقدار اصلی برگردانده می‌شود.
    """
    env = dict(os.environ)
    if is_frozen() and system() == "linux":
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = original
    return env


def launch(args):
    """یک برنامهٔ دیگر را اجرا می‌کند، بدون پنجرهٔ سیاه در ویندوز."""
    subprocess.run(args, check=False, env=run_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ---------------------------------------------------------------------------
# پنجرهٔ انتخاب فایل
# ---------------------------------------------------------------------------

WINDOWS_DIALOG = """
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object Windows.Forms.Form -Property @{TopMost = $true}
$dialog = New-Object Windows.Forms.%s
$dialog.%s = $env:DIBACHEH_PROMPT
if ($dialog.ShowDialog($owner) -eq 'OK') { $dialog.%s } else { exit 1 }
"""


def browse_command(kind, prompt):
    """دستور پنجرهٔ انتخاب. kind: file یا folder. روی لینوکس بدون ابزار لازم، None."""
    folder = kind == "folder"
    if system() == "mac":
        # متن داخل AppleScript قرار می‌گیرد، پس علامت " از آن حذف می‌شود
        safe = prompt.replace('"', "").replace("\\", "")
        what = "folder" if folder else "file"
        # activate باعث می‌شود پنجره جلوی مرورگر باز شود
        return ["osascript", "-e", "activate", "-e", f'POSIX path of (choose {what} with prompt "{safe}")']
    if system() == "windows":
        parts = (("FolderBrowserDialog", "Description", "SelectedPath") if folder
                 else ("OpenFileDialog", "Title", "FileName"))
        return ["powershell", "-NoProfile", "-STA", "-Command", WINDOWS_DIALOG % parts]
    if shutil.which("zenity"):
        return ["zenity", "--file-selection", "--title", prompt] + (["--directory"] if folder else [])
    if shutil.which("kdialog"):
        return ["kdialog", "--title", prompt, "--getexistingdirectory" if folder else "--getopenfilename", str(Path.home())]
    return None


def choose(kind="file", prompt="یک فایل انتخاب کنید"):
    """پنجرهٔ انتخاب خود سیستم را باز می‌کند و آدرس کامل را برمی‌گرداند.

    مرورگر به دلایل امنیتی آدرس کامل فایل را نمی‌دهد، برای همین این کار در پایتون انجام می‌شود.
    خروجی None یعنی کاربر Cancel زد.
    """
    command = browse_command(kind, prompt)
    if command is None:
        raise BrowseUnavailable("برای انتخاب فایل، بستهٔ zenity یا kdialog را نصب کنید.")
    result = subprocess.run(
        command, capture_output=True, encoding="utf-8", errors="replace",
        env={**run_env(), "DIBACHEH_PROMPT": prompt},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    if kind == "folder" and len(path) > 1:
        path = path.rstrip("/")
    return path or None
