"""نسخهٔ نصبی ویندوز و لینوکس را می‌سازد.

    python tools/build_release.py

خروجی در build/release:
    ویندوز: برنامهٔ نصب (با Inno Setup) و یک zip قابل حمل
    لینوکس: AppImage (با appimagetool) و یک tar.gz

در Mac این فایل فقط پوشهٔ سرور را می‌سازد و بقیهٔ کار با tools/build_release.sh است،
تا فهرست فایل‌ها و کتابخانه‌های لازم فقط یک جا نوشته شده باشد.
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "release"
VERSION = (ROOT / "VERSION").read_text().strip()
WINDOWS = sys.platform.startswith("win")
SEP = ";" if WINDOWS else ":"
APPIMAGETOOL = "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
APPIMAGE_RUNTIME = "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"


def run(*args, **kwargs):
    print("+", *args, flush=True)
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def download(url, target, attempts=4):
    """سرور گاهی موقتاً جواب نمی‌دهد؛ قبل از خطا دادن چند بار امتحان می‌کند."""
    for attempt in range(1, attempts + 1):
        try:
            urllib.request.urlretrieve(url, target)
            return
        except OSError as error:   # خطاهای شبکه و HTTP همه از این نوع‌اند
            if attempt == attempts:
                raise
            print(f"دانلود نشد ({error}). تلاش دوباره...", flush=True)
            time.sleep(20 * attempt)


def pyinstaller(*options):
    """برنامه با پایتون و همهٔ کتابخانه‌ها در یک پوشه. کتابخانهٔ تازه را اینجا اضافه کنید."""
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", *options,
        "--distpath", OUT / "dist", "--workpath", OUT / "work", "--specpath", OUT / "work",
        "--add-data", f"{ROOT / 'templates'}{SEP}templates", "--add-data", f"{ROOT / 'static'}{SEP}static",
        "--collect-all", "pypdfium2", "--collect-all", "pypdfium2_raw",
        "--hidden-import", "PIL.Image", "--hidden-import", "markdown.extensions.tables",
        "--hidden-import", "markdown.extensions.fenced_code", "--hidden-import", "markdown.extensions.sane_lists",
        "--hidden-import", "markdown.extensions.nl2br",
        ROOT / "app.py", cwd=ROOT)


def build_bundle():
    """نسخهٔ پنجره‌دار ویندوز و لینوکس، با آیکون و مجوزها."""
    icon = OUT / ("icon.ico" if WINDOWS else "icon.png")
    run(sys.executable, ROOT / "tools" / "make_icon.py", icon)
    pyinstaller("--windowed", "--name", "Dibacheh", "--icon", icon)
    bundle = OUT / "dist" / "Dibacheh"
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy(ROOT / name, bundle / name)
    return bundle


def package_windows(bundle):
    shutil.make_archive(str(OUT / f"Dibacheh-{VERSION}-Windows-Portable"), "zip", bundle.parent, bundle.name)
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    run(iscc, ROOT / "tools" / "windows_installer.iss", env={**os.environ, "DIBACHEH_VERSION": VERSION})


def package_linux(bundle):
    with tarfile.open(OUT / f"Dibacheh-{VERSION}-Linux-x86_64.tar.gz", "w:gz") as archive:
        archive.add(bundle, arcname="Dibacheh")
    appdir = OUT / "Dibacheh.AppDir"
    shutil.copytree(bundle, appdir / "usr" / "lib" / "dibacheh")
    (appdir / "AppRun").write_text('#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/usr/lib/dibacheh/Dibacheh" "$@"\n')
    (appdir / "AppRun").chmod(0o755)
    (appdir / "dibacheh.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Dibacheh\nExec=AppRun\nIcon=dibacheh\nCategories=Education;\n")
    shutil.copy(ROOT / "tools" / "icon.png", appdir / "dibacheh.png")
    tool = OUT / "appimagetool"
    download(APPIMAGETOOL, tool)
    tool.chmod(0o755)
    runtime = OUT / "appimage-runtime"
    download(APPIMAGE_RUNTIME, runtime)   # وگرنه خود appimagetool آن را بدون تلاش دوباره می‌گیرد
    run(tool, "--appimage-extract-and-run", "--runtime-file", runtime, appdir, OUT / f"Dibacheh-{VERSION}-Linux-x86_64.AppImage",
        env={**os.environ, "ARCH": platform.machine()})


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    if sys.platform == "darwin":   # پوستهٔ Mac و dmg را tools/build_release.sh می‌سازد
        pyinstaller("--console", "--name", "dibacheh-server")
        return
    bundle = build_bundle()
    (package_windows if WINDOWS else package_linux)(bundle)
    print("ساخته شد:", *[p.name for p in OUT.iterdir() if p.is_file()])


if __name__ == "__main__":
    main()
