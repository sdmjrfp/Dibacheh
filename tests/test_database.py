"""تست‌های دیتابیس، migration و backup."""

import sqlite3
from datetime import date, datetime, timedelta

import pytest

import database
import leitner
import scheduler

NOW = datetime(2026, 1, 3, 10, 0)


def test_new_database_gets_latest_version(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(database.MIGRATIONS)


def test_reopening_keeps_data(tmp_path):
    path = tmp_path / "db.sqlite3"
    first = database.connect(path)
    database.add_item(first, "زبان", 3, 60, now=NOW)
    first.close()
    second = database.connect(path)          # migration دوباره اجرا نمی‌شود
    assert [i["title"] for i in database.list_items(second)] == ["زبان"]
    second.close()


def test_new_migration_runs_once_and_keeps_data(tmp_path, monkeypatch):
    path = tmp_path / "db.sqlite3"
    conn = database.connect(path)
    database.add_item(conn, "زبان", 1, 60, now=NOW)
    conn.close()
    monkeypatch.setattr(database, "MIGRATIONS",
                        database.MIGRATIONS + ["ALTER TABLE items ADD COLUMN notes TEXT;"])
    conn = database.connect(path)
    conn.close()
    conn = database.connect(path)            # دوباره وصل شدن نباید خطا بدهد
    assert database.list_items(conn)[0]["title"] == "زبان"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(database.MIGRATIONS)
    conn.close()


def test_add_item_creates_sessions_and_goes_to_end_of_queue(conn):
    a = database.add_item(conn, "A", 3, 60, now=NOW)
    b = database.add_item(conn, "B", 2, 45, now=NOW)
    items = database.list_items(conn)
    assert [i["id"] for i in items] == [a, b]
    assert items[1]["queue_position"] > items[0]["queue_position"]
    sess = database.list_sessions(conn, b)
    assert [(s["sequence"], s["minutes"], s["status"]) for s in sess] == [(1, 45, "unread"), (2, 45, "unread")]


def test_reorder_items(conn):
    a = database.add_item(conn, "A", 1, 60, now=NOW)
    b = database.add_item(conn, "B", 1, 60, now=NOW)
    database.reorder_items(conn, [b, a])
    assert [i["id"] for i in database.list_items(conn)] == [b, a]


def test_dates_and_lists_round_trip(conn):
    item_id = database.add_item(
        conn, "ورزش", 10, 10, now=NOW, item_type="routine",
        start_date=date(2026, 1, 5), routine_weekdays=[5, 0], target_date=date(2026, 3, 1),
        review_intervals=[2, 5],
    )
    it = database.get_item(conn, item_id)
    assert it["start_date"] == date(2026, 1, 5)
    assert it["routine_weekdays"] == [5, 0]
    assert it["review_intervals"] == [2, 5]
    assert it["is_active"] is True


def test_unknown_field_is_rejected(conn):
    item_id = database.add_item(conn, "A", 1, 60, now=NOW)
    with pytest.raises(ValueError):
        database.update_item(conn, item_id, title="x", queue_position_hack=1)


def test_delete_item_removes_sessions_and_log(conn):
    item_id = database.add_item(conn, "A", 2, 60, now=NOW)
    sid = database.list_sessions(conn, item_id)[0]["id"]
    database.add_log(conn, sid, date(2026, 1, 3), "read", 60, "done")
    database.delete_item(conn, item_id)
    assert database.list_sessions(conn) == []
    assert database.list_log(conn) == []


def test_deleting_category_keeps_items(conn):
    cat = database.add_category(conn, "زبان")
    item_id = database.add_item(conn, "A", 1, 60, now=NOW, category_id=cat)
    database.delete_category(conn, cat)
    assert database.get_item(conn, item_id)["category_id"] is None


def test_settings_defaults_and_changes(conn):
    s = database.get_settings(conn)
    assert s["review_intervals"] == [1, 3, 7, 30]
    assert s["cap_tolerance_minutes"] == 30
    database.set_setting(conn, "review_intervals", [2, 4])
    assert database.get_settings(conn)["review_intervals"] == [2, 4]
    with pytest.raises(ValueError):
        database.set_setting(conn, "no_such_setting", 1)


def test_day_overrides(conn):
    database.set_day_override(conn, date(2026, 1, 5), 0)
    assert database.get_day_overrides(conn) == {date(2026, 1, 5): 0}
    database.set_day_override(conn, date(2026, 1, 5), None)
    assert database.get_day_overrides(conn) == {}


def test_plan_from_database_matches_base_scenario(conn):
    """سناریوی پایه، این بار از راه دیتابیس واقعی."""
    database.add_item(conn, "A", 3, 60, now=NOW)
    database.add_item(conn, "B", 2, 60, now=NOW)
    inputs = database.load_plan_inputs(conn)
    plan = scheduler.build_plan(inputs["items"], inputs["sessions"], inputs["settings"],
                                inputs["day_overrides"], date(2026, 1, 3))
    assert [d["total"] for d in plan["days"][:5]] == [120, 100, 140, 40, 40]


def test_session_progress_is_saved(conn):
    item_id = database.add_item(conn, "A", 1, 60, now=NOW)
    s = database.list_sessions(conn, item_id)[0]
    done = leitner.finish_reading(s, date(2026, 1, 3), [1, 3, 7, 30])
    fields = {k: done[k] for k in database.SESSION_FIELDS if k in done}
    database.update_session(conn, s["id"], **fields)
    saved = database.list_sessions(conn, item_id)[0]
    assert saved["status"] == "reviewing"
    assert saved["next_review_on"] == date(2026, 1, 4)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def test_backup_once_per_day_and_is_valid(conn, tmp_path):
    database.add_item(conn, "A", 1, 60, now=NOW)
    folder = tmp_path / "backups"
    first = database.daily_backup(conn, folder, 30, date(2026, 1, 3))
    assert first is not None and first.exists()
    assert database.daily_backup(conn, folder, 30, date(2026, 1, 3)) is None  # همان روز دوباره نه
    copy = sqlite3.connect(first)
    assert copy.execute("SELECT title FROM items").fetchone()[0] == "A"
    copy.close()


def test_backup_keeps_only_last_n(conn, tmp_path):
    folder = tmp_path / "backups"
    folder.mkdir()
    (folder / "my-notes.txt").write_text("فایل کاربر")   # فایل دیگر نباید پاک شود
    for n in range(35):
        database.daily_backup(conn, folder, 30, date(2026, 1, 1) + timedelta(days=n))
    files = sorted(folder.glob("dibacheh-*.sqlite3"))
    assert len(files) == 30
    assert files[0].name == "dibacheh-2026-01-06.sqlite3"   # 5 نسخهٔ قدیمی پاک شد
    assert (folder / "my-notes.txt").exists()


def test_backup_folder_relative_to_project():
    folder = database.backup_folder({"backup_folder": "data/backups"})
    assert folder == database.PROJECT_DIR / "data" / "backups"


def test_simultaneous_first_requests_do_not_break_new_database(tmp_path):
    """مرورگر اولین بار چند درخواست را با هم می‌فرستد؛ ساختن جدول‌ها نباید دو بار اجرا شود."""
    import threading

    path = tmp_path / "fresh.sqlite3"
    errors = []

    def open_db():
        try:
            database.connect(path).close()
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=open_db) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_transaction_saves_all_or_nothing(conn):
    with pytest.raises(RuntimeError):
        with database.transaction(conn):
            database.add_item(conn, "A", 1, 60, now=NOW)
            raise RuntimeError("وسط کار")
    assert database.list_items(conn) == []
    with database.transaction(conn):
        with database.transaction(conn):       # تودرتو
            database.add_item(conn, "B", 1, 60, now=NOW)
    conn.rollback()
    assert [i["title"] for i in database.list_items(conn)] == ["B"]


def test_failed_request_leaves_no_half_saved_data(client):
    # درس ساخته می‌شود، ولی وابستگی‌اش نامعتبر است: نباید هیچ چیزی ذخیره شود
    response = client.post("/api/items", json={"title": "نیمه‌کاره", "session_count": 1, "session_minutes": 30,
                                                 "requires": [{"id": 999}]})
    assert response.status_code == 400
    assert client.get("/api/state").get_json()["items"] == []


def test_undo_snapshot_is_small_for_a_large_plan(client):
    import undo
    for n in range(20):
        client.post("/api/items", json={"title": f"درس {n}", "session_count": 30, "session_minutes": 30})
    size = len(undo.stack[-1][1])
    assert size < 40_000


def test_corrupt_backup_is_not_kept(conn, tmp_path, monkeypatch):
    folder = tmp_path / "backups"
    good = database.daily_backup(conn, folder, 30, date(2026, 1, 1))
    assert database.integrity_problem(good) is None
    monkeypatch.setattr(database, "integrity_problem", lambda path: "خراب")
    with pytest.raises(database.BackupError):
        database.daily_backup(conn, folder, 1, date(2026, 1, 2))
    assert [f.name for f in folder.iterdir()] == [good.name]    # نسخهٔ سالم پاک نشد


def test_broken_file_is_detected(tmp_path):
    broken = tmp_path / "x.sqlite3"
    broken.write_bytes(b"SQLite format 3\0" + b"\xff" * 4096)
    assert database.integrity_problem(broken)
    with pytest.raises(ValueError):
        database.check_database_file(broken)
