"""تست‌های پایهٔ سرور: صفحهٔ اصلی باز شود و تنظیمات امنیتی درست باشد."""

import re
from pathlib import Path

import app as app_module
import config
import scheduler


def test_index_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # صفحه باید فارسی و راست‌به‌چپ باشد
    assert 'dir="rtl"' in html
    assert 'lang="fa"' in html


def test_server_only_listens_on_this_mac():
    assert config.HOST == "127.0.0.1"


def test_page_has_no_external_links(client):
    # برنامه نباید به CDN، فونت آنلاین یا هیچ آدرس اینترنتی وابسته باشد
    html = client.get("/").get_data(as_text=True)
    assert not re.search(r'(src|href)\s*=\s*"(https?:)?//', html)
    static = Path(app_module.app.static_folder)
    for path in [*static.rglob("*.css"), *static.rglob("*.js")]:
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


def test_unexpected_error_is_logged_and_gives_clean_message(client, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("خرابی آزمایشی")
    monkeypatch.setattr(scheduler, "build_plan", broken)
    response = client.get("/api/state")
    assert response.status_code == 500
    assert "گزارش خطا" in response.get_json()["error"]
    assert "خرابی آزمایشی" not in response.get_json()["error"]   # جزئیات فقط در گزارش
    assert "خرابی آزمایشی" in caplog.text


def test_failed_page_load_keeps_http_errors(client):
    assert client.get("/no-such-page").status_code == 404


def test_log_endpoints(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "log_file", lambda: tmp_path / "logs" / "x.log")
    assert client.get("/api/logs").get_json()["lines"] == []
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "x.log").write_text("\n".join(str(n) for n in range(300)), encoding="utf-8")
    lines = client.get("/api/logs").get_json()["lines"]
    assert len(lines) == 200 and lines[-1] == "299"
    assert client.post("/api/logs/client", json={"message": "m", "source": "s", "line": 1}).status_code == 200


def test_setup_logging_writes_to_file(tmp_path, monkeypatch):
    import logging
    monkeypatch.setattr(config, "log_file", lambda: tmp_path / "logs" / "x.log")
    root = logging.getLogger()
    before = list(root.handlers)
    config.setup_logging()
    try:
        root.error("پیام آزمایشی")
        assert "پیام آزمایشی" in (tmp_path / "logs" / "x.log").read_text(encoding="utf-8")
    finally:
        for handler in [h for h in root.handlers if h not in before]:
            root.removeHandler(handler)
            handler.close()
