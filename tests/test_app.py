"""تست‌های پایهٔ سرور: صفحهٔ اصلی باز شود و تنظیمات امنیتی درست باشد."""

import re
from pathlib import Path

import app as app_module


def test_index_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # صفحه باید فارسی و راست‌به‌چپ باشد
    assert 'dir="rtl"' in html
    assert 'lang="fa"' in html


def test_server_only_listens_on_this_mac():
    assert app_module.HOST == "127.0.0.1"


def test_page_has_no_external_links(client):
    # برنامه نباید به CDN، فونت آنلاین یا هیچ آدرس اینترنتی وابسته باشد
    html = client.get("/").get_data(as_text=True)
    assert not re.search(r'(src|href)\s*=\s*"(https?:)?//', html)
    static = Path(app_module.app.static_folder)
    for path in [*static.glob("*.css"), *static.glob("*.js")]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r'url\(\s*["\']?(https?:)?//', text), path.name
        assert not re.search(r'(import|fetch)\s*\(\s*["\']https?://', text), path.name


def test_first_request_makes_daily_backup(client, tmp_path):
    client.get("/")
    assert len(list((tmp_path / "backups").glob("dibacheh-*.sqlite3"))) == 1


def test_api_plan_returns_json(client):
    data = client.get("/api/plan").get_json()
    # دیتابیس خالی: فقط امروز، بدون کار
    assert len(data["days"]) == 1
    assert data["days"][0]["tasks"] == []
    assert data["warnings"] == []
