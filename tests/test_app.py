"""تست‌های پایهٔ سرور: صفحهٔ اصلی باز شود و تنظیمات امنیتی درست باشد."""

import app as app_module


def test_index_page_loads():
    client = app_module.app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # صفحه باید فارسی و راست‌به‌چپ باشد
    assert 'dir="rtl"' in html
    assert 'lang="fa"' in html


def test_server_only_listens_on_this_mac():
    assert app_module.HOST == "127.0.0.1"


def test_page_has_no_external_links():
    # برنامه نباید به CDN یا هیچ آدرس اینترنتی وابسته باشد
    html = app_module.app.test_client().get("/").get_data(as_text=True)
    assert "http://" not in html
    assert "https://" not in html
