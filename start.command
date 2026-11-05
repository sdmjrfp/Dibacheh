#!/bin/zsh
# اجرای برنامه با دوبار کلیک. (نسخهٔ ساده؛ در مرحلهٔ ۸ کامل می‌شود.)
cd "$(dirname "$0")"
(sleep 1.5; open "http://127.0.0.1:5000") &
.venv/bin/python app.py
