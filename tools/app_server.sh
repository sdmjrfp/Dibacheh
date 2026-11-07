#!/bin/zsh
# سرور دیباچه را برای Dibacheh.app روشن و خاموش می‌کند.
#   start: اگر سرور باز نیست، در پس‌زمینه اجرا می‌کند و صبر می‌کند تا آماده شود.
#   open:  صفحهٔ برنامه را در مرورگر پیش‌فرض باز می‌کند.
#   stop:  سروری را که خود app اجرا کرده می‌بندد.
# خروجی 2 = برنامه نصب نشده، 3 = برنامهٔ دیگری پورت را گرفته، 4 = سرور بالا نیامد.
#
# این فایل در دو جا اجرا می‌شود: داخل پروژه (با پایتون .venv)، و داخل نسخهٔ نصبی
# Dibacheh.app کنار سرور آماده (dibacheh-server).

HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$HERE/dibacheh-server/dibacheh-server" ]; then
  SERVER=("$HERE/dibacheh-server/dibacheh-server")
  STATE="${DIBACHEH_HOME:-$HOME/Library/Application Support/Dibacheh}/data"
  PORT="${DIBACHEH_PORT:-5847}"
else
  cd "$HERE/.."
  SERVER=(.venv/bin/python app.py)
  STATE="data"
  PORT="${DIBACHEH_PORT:-5000}"
fi
export DIBACHEH_PORT="$PORT"
URL="http://127.0.0.1:$PORT"
PID_FILE="$STATE/app-$PORT.pid"

is_dibacheh() {
  curl -s --noproxy '*' --max-time 2 "$URL/" | grep -q 'name="csrf-token"'
}

case "$1" in
  start)
    [ -x "${SERVER[1]}" ] || exit 2
    is_dibacheh && exit 0
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && exit 3
    mkdir -p "$STATE"
    nohup "${SERVER[@]}" >"$STATE/app-$PORT.log" 2>&1 &
    echo $! >"$PID_FILE"
    for i in {1..50}; do
      is_dibacheh && exit 0
      sleep 0.2
    done
    exit 4
    ;;
  open)
    [ -n "$DIBACHEH_NO_BROWSER" ] || open "$URL"
    ;;
  stop)
    if [ -f "$PID_FILE" ]; then
      kill "$(cat "$PID_FILE")" 2>/dev/null
      rm -f "$PID_FILE"
    fi
    ;;
esac
