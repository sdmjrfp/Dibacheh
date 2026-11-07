#!/bin/zsh
# نسخهٔ نصبی را می‌سازد: Dibacheh.app که پایتون هم داخلش است، و یک فایل dmg.
#     zsh tools/build_release.sh
# خروجی در build/release است. فقط برای همان نوع پردازنده‌ای ساخته می‌شود که با آن build می‌کنید.

set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"
VERSION="$(cat VERSION)"
OUT="build/release"
ARCH="$(uname -m)"
[ "$ARCH" = "arm64" ] && LABEL="AppleSilicon" || LABEL="Intel"

rm -rf "$OUT"
mkdir -p "$OUT"
.venv/bin/pip install -q -r requirements.txt -r requirements-build.txt

# ۱. سرور با پایتون و همهٔ کتابخانه‌ها در یک پوشه
.venv/bin/pyinstaller --noconfirm --clean --onedir --console --name dibacheh-server \
  --distpath "$OUT/dist" --workpath "$OUT/work" --specpath "$OUT/work" \
  --add-data "$ROOT/templates:templates" --add-data "$ROOT/static:static" \
  --collect-all pypdfium2 --collect-all pypdfium2_raw \
  --hidden-import PIL.Image --hidden-import markdown.extensions.tables \
  --hidden-import markdown.extensions.fenced_code --hidden-import markdown.extensions.sane_lists \
  --hidden-import markdown.extensions.nl2br \
  app.py

# ۲. پوستهٔ Mac: آیکون Dock و Quit
APP="$OUT/Dibacheh.app"
osacompile -s -o "$APP" tools/Dibacheh.applescript
.venv/bin/python tools/make_icon.py "$APP/Contents/Resources/applet.icns"
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName Dibacheh" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string local.dibacheh.app" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier local.dibacheh.app" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST"
cp -R "$OUT/dist/dibacheh-server" "$APP/Contents/Resources/dibacheh-server"
cp tools/app_server.sh LICENSE THIRD_PARTY_NOTICES.md "$APP/Contents/Resources/"
chmod +x "$APP/Contents/Resources/app_server.sh"
codesign --force --deep --sign - "$APP"

# ۳. فایل dmg با میان‌بر Applications
STAGE="$OUT/stage"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp tools/install-guide.txt "$STAGE/راهنمای نصب.txt"
DMG="$OUT/Dibacheh-$VERSION-$LABEL.dmg"
hdiutil create -quiet -volname "Dibacheh" -srcfolder "$STAGE" -format UDZO -ov "$DMG"
echo "ساخته شد: $DMG"
du -sh "$APP" "$DMG"
