#!/bin/zsh
# اجرای دیباچه با دوبار کلیک.
#
# این پنجرهٔ Terminal تا وقتی برنامه باز است باز می‌ماند.
# برای بستن برنامه، همین پنجره را ببندید یا Ctrl+C بزنید.

cd "$(dirname "$0")"
URL="http://127.0.0.1:5000"

# آیا نصب اولیه انجام شده است؟
if [ ! -x .venv/bin/python ]; then
  echo "برنامه هنوز نصب نشده است. راهنمای «نصب» در README.md را ببینید."
  echo "برای بستن، Enter بزنید."
  read
  exit 1
fi

# اگر دیباچه از قبل باز است، فقط مرورگر را باز کن
if curl -s --max-time 2 "$URL/" | grep -q 'name="csrf-token"'; then
  echo "دیباچه از قبل در حال اجراست. مرورگر باز می‌شود."
  open "$URL"
  exit 0
fi

# اگر برنامهٔ دیگری پورت 5000 را گرفته باشد
if lsof -nP -iTCP:5000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "برنامهٔ دیگری پورت 5000 را گرفته است."
  echo "اگر AirPlay Receiver در System Settings روشن است، آن را خاموش کنید و دوباره امتحان کنید."
  echo "برای بستن، Enter بزنید."
  read
  exit 1
fi

# وقتی سرور آماده شد، مرورگر پیش‌فرض Mac باز می‌شود
(
  for i in {1..50}; do
    curl -s --max-time 1 -o /dev/null "$URL/" && break
    sleep 0.2
  done
  open "$URL"
) &

echo "دیباچه اجرا شد: $URL"
echo "برای بستن برنامه، این پنجره را ببندید یا Ctrl+C بزنید."
echo
exec .venv/bin/python app.py
