#!/bin/zsh
# Dibacheh.app را داخل پوشهٔ پروژه می‌سازد. فقط یک بار لازم است:
#     zsh tools/build_app.sh
# بعد آیکون را به Dock بکشید. خود Dibacheh.app باید داخل پوشهٔ پروژه بماند.

set -e
cd "$(dirname "$0")/.."
APP="Dibacheh.app"
rm -rf "$APP"
osacompile -s -o "$APP" tools/Dibacheh.applescript          # -s: برنامه باز می‌ماند تا Quit شود
.venv/bin/python tools/make_icon.py "$APP/Contents/Resources/applet.icns"
/usr/libexec/PlistBuddy -c "Set :CFBundleName Dibacheh" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string local.dibacheh.app" "$APP/Contents/Info.plist" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier local.dibacheh.app" "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP"                     # بعد از تغییر آیکون، امضای محلی تازه
echo "ساخته شد: $PWD/$APP"
