"""نسخهٔ ساخته‌شده را واقعاً اجرا می‌کند و کارهای اصلی را امتحان می‌کند.

    python tools/smoke_test.py <فایل اجرایی برنامه>

درس با PDF و نوت می‌سازد، خروجی می‌گیرد و می‌بندد. این تست مطمئن می‌شود چیزی
(مثل کتابخانهٔ PDF یا فونت‌ها) از بستهٔ نصبی جا نیفتاده است.
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pypdfium2 as pdfium

PORT = 5899
URL = f"http://127.0.0.1:{PORT}"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(path):
    with OPENER.open(URL + path, timeout=30) as response:
        return response.read()


def send(method, path, token, body):
    request = urllib.request.Request(URL + path, data=json.dumps(body).encode(), method=method, headers={
        "X-CSRF-Token": token, "Content-Type": "application/json"})
    with OPENER.open(request, timeout=60) as response:
        return json.load(response)


def main(binary):
    work = Path(tempfile.mkdtemp())
    doc = pdfium.PdfDocument.new()
    for _ in range(4):
        doc.new_page(300, 400)
    buffer = io.BytesIO()
    doc.save(buffer)
    pdf = work / "کتاب نمونه.pdf"
    pdf.write_bytes(buffer.getvalue())
    note = work / "note.md"
    note.write_text("# فصل ۱\nمتن اول\n", encoding="utf-8")

    env = {**os.environ, "DIBACHEH_HOME": str(work / "home"), "DIBACHEH_PORT": str(PORT),
           "DIBACHEH_NO_LAUNCH": "1", "APPIMAGE_EXTRACT_AND_RUN": "1"}
    server = subprocess.Popen([binary], env=env)
    try:
        for _ in range(120):
            try:
                page = get("/").decode("utf-8")
                break
            except (urllib.error.URLError, OSError):
                if server.poll() is not None:
                    sys.exit(f"برنامه با کد {server.returncode} بسته شد")
                time.sleep(0.5)
        else:
            sys.exit("برنامه بالا نیامد")
        token = re.search(r'csrf-token" content="([^"]+)"', page).group(1)
        assert get("/static/style.css") and get("/static/vendor/fonts/samim/Samim.woff2")
        send("PATCH", "/api/settings", token, {"export_folder": str(work / "out"), "font_family": "Samim"})
        send("POST", "/api/items", token, {
            "title": "کتاب", "session_count": 2, "session_minutes": 60, "section_unit": "page",
            "range_start": "1", "range_end": "4", "source_type": "file", "source_path_or_url": str(pdf)})
        state = send("POST", "/api/items", token, {
            "title": "نوت", "session_count": 1, "session_minutes": 30,
            "source_type": "file", "source_path_or_url": str(note)})
        assert state["plan"]["days"][0]["tasks"], "برنامه خالی است"
        name = send("POST", "/api/export", token, {"scope": "day", "with_content": True})["name"]
        html = (work / "out" / name).read_text(encoding="utf-8")
        assert html.count("data:image/jpeg") == 2, "صفحه‌های PDF در خروجی نیست"
        assert "<h1>فصل ۱</h1>" in html, "Markdown تبدیل نشده"
        assert 'font-family: "Samim"' in html, "فونت در خروجی نیست"
        assert send("POST", "/api/data/export", token, {})["name"].endswith(".zip")
        assert json.loads(get("/api/stats?period=all"))["summary"]["period"] == "all"
        assert (work / "home" / "data" / "dibacheh.sqlite3").exists(), "داده‌ها در پوشهٔ درست نیستند"
        if state["can_quit"]:
            send("POST", "/api/quit", token, {})
            server.wait(timeout=15)
        print("OK:", state["system"], binary)
    finally:
        if server.poll() is None:
            server.kill()


if __name__ == "__main__":
    main(sys.argv[1])
