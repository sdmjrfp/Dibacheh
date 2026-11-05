"""سرور محلی برنامه.

این فایل فقط صفحه‌ها و مسیرها (route) را تعریف می‌کند.
منطق اصلی در فایل‌های دیگر است:
  scheduler.py  موتور چینش برنامه
  leitner.py    قانون‌های جعبه و مرور
  database.py   کار با SQLite
  sources.py    منابع درسی و Browse
  exporter.py   ساخت خروجی HTML

اجرا:
    .venv/bin/python app.py
بعد در مرورگر به آدرس http://127.0.0.1:5000 بروید.
"""

from flask import Flask, render_template

# آدرس و پورت سرور.
# 127.0.0.1 یعنی فقط خود همین Mac می‌تواند به برنامه وصل شود،
# نه گوشی یا کامپیوتر دیگری در شبکه.
HOST = "127.0.0.1"
PORT = 5000

app = Flask(__name__)


@app.route("/")
def index():
    """صفحهٔ اصلی داشبورد."""
    return render_template("index.html")


if __name__ == "__main__":
    # debug خاموش است، چون حالت debug اجازهٔ اجرای کد از راه مرورگر را می‌دهد.
    app.run(host=HOST, port=PORT, debug=False)
