"""تنظیمات مشترک تست‌ها.

تست‌ها هرگز به دیتابیس واقعی شما در data/ دست نمی‌زنند.
هر تست یک دیتابیس و پوشهٔ backup موقت جدا می‌گیرد که بعد از تست پاک می‌شود.
"""

import sys
from pathlib import Path

import pytest
from flask.testing import FlaskClient

# تا تست‌ها بتوانند «from helpers import ...» بنویسند
sys.path.insert(0, str(Path(__file__).parent))

import app as app_module  # noqa: E402
import database  # noqa: E402


class LocalClient(FlaskClient):
    """مثل مرورگر روی همین Mac، درخواست‌ها را به آدرس 127.0.0.1:5000 می‌فرستد."""

    def open(self, *args, **kwargs):
        kwargs.setdefault("base_url", f"http://127.0.0.1:{app_module.PORT}")
        return super().open(*args, **kwargs)


@pytest.fixture
def conn(tmp_path):
    connection = database.connect(tmp_path / "test.sqlite3")
    yield connection
    connection.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    setup = database.connect(db_path)
    database.set_setting(setup, "backup_folder", str(tmp_path / "backups"))
    setup.close()
    app_module.app.config["DB_PATH"] = db_path
    app_module._last_backup_day = None
    app_module._undo_stack.clear()
    app_module._redo_stack.clear()
    app_module.app.test_client_class = LocalClient
    test_client = app_module.app.test_client()
    # مثل صفحهٔ خود برنامه: رمز CSRF همراه هر درخواست
    test_client.environ_base["HTTP_X_CSRF_TOKEN"] = app_module.CSRF_TOKEN
    yield test_client
    app_module.app.config["DB_PATH"] = database.DB_PATH
