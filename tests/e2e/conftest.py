"""آزمون رابط کاربری در مرورگر واقعی (Chromium بدون پنجره، با Playwright).

برای هر تست یک سرور واقعی با دیتابیس موقت اجرا می‌شود، پس به داده‌های شما دست نمی‌زند.
اگر Playwright نصب نباشد، این تست‌ها skip می‌شوند.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            instance = p.chromium.launch()
        except sync_api.Error as error:
            pytest.skip(f"مرورگر Playwright نصب نیست: {error}")
        yield instance
        instance.close()


@pytest.fixture
def server(tmp_path):
    """سرور واقعی با دیتابیس و پوشهٔ خروجی موقت."""
    port = free_port()
    env = {**os.environ, "DIBACHEH_DB": str(tmp_path / "e2e.sqlite3"), "DIBACHEH_PORT": str(port)}
    process = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(100):
        try:
            opener.open(url, timeout=1).read()
            break
        except OSError:
            time.sleep(0.1)
    else:
        process.kill()
        pytest.fail("سرور بالا نیامد")
    yield url
    process.kill()
    process.wait()


class App:
    """کارهای پرتکرار روی صفحه."""

    def __init__(self, page, url):
        self.page = page
        self.url = url

    def open(self):
        self.page.goto(self.url)
        self.page.wait_for_selector("#today:not(:empty)")
        return self

    def call(self, method, path, body=None):
        """همان درخواستی که صفحه می‌فرستد؛ برای آماده کردن داده."""
        return self.page.evaluate(
            """async ([method, path, body]) => {
              const token = document.querySelector('meta[name="csrf-token"]').content;
              const r = await fetch(path, {method, headers: {'X-CSRF-Token': token, 'Content-Type': 'application/json'},
                                           body: body === null ? undefined : JSON.stringify(body)});
              return r.json();
            }""", [method, path, body])

    def add(self, title, count=1, minutes=60, **extra):
        return self.call("POST", "/api/items", {"title": title, "session_count": count, "session_minutes": minutes, **extra})

    def reload(self):
        return self.open()

    def titles(self):
        return self.page.locator(".item .title").all_inner_texts()

    def day_tasks(self, selector=".cal-day.today"):
        return [t.strip() for t in self.page.locator(f"{selector} .task:not(.done) .task-title").all_inner_texts()]

    def done_tasks(self, selector=".cal-day.today"):
        return [t.strip() for t in self.page.locator(f"{selector} .task.done .task-title").all_inner_texts()]

    def settle(self):
        """صبر تا تمام شدن درخواست‌ها و انیمیشن‌ها."""
        # networkidle اینجا به درد نمی‌خورد: یک بار که برقرار شد، دیگر منتظر درخواست تازه نمی‌ماند.
        self.page.wait_for_function("window.pendingRequests === 0")
        self.page.wait_for_timeout(450)

    def drag(self, source, target_x, target_y):
        box = source.bounding_box()
        mouse = self.page.mouse
        mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        mouse.down()
        mouse.move(target_x, target_y, steps=12)
        return mouse


@pytest.fixture
def app(browser, server):
    context = browser.new_context(viewport={"width": 1600, "height": 1000}, locale="fa-IR")
    # شمارش درخواست‌های در جریان، برای App.settle
    context.add_init_script("""
      window.pendingRequests = 0;
      const realFetch = window.fetch;
      window.fetch = async (...args) => {
        window.pendingRequests++;
        try { return await realFetch(...args); } finally { window.pendingRequests--; }
      };
    """)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "400" not in m.text else None)
    page.on("dialog", lambda dialog: dialog.accept(dialog.default_value or "الگوی آزمایشی"))
    app_page = App(page, server).open()
    app_page.call("PATCH", "/api/settings", {"setup_done": True})
    app_page.open()
    yield app_page
    context.close()
    assert errors == [], f"خطا در مرورگر: {json.dumps(errors, ensure_ascii=False)}"
