"""تست‌های وابستگی، تعطیلی چندروزه، یادداشت، بایگانی، افزودن گروهی، ساختار فایل،
آمار، برگرداندن backup و انتقال داده‌ها."""

import io
import sqlite3
import zipfile
from datetime import date, timedelta

import pypdfium2 as pdfium
from helpers import DAY1, d, day_of, item, sessions, settings
from test_api import add, item_named
from test_calendar_api import days_of, today_of
from test_progress_api import done, session_of

import database
import scheduler
import sources

# ---------------------------------------------------------------------------
# موتور: وابستگی
# ---------------------------------------------------------------------------

def plan(items, sess, **extra):
    return scheduler.build_plan(items, sess, settings(default_cap_minutes=240, **extra), {}, DAY1)


def test_dependent_starts_day_after_prerequisite_reading_ends():
    items = [item("B", 1, requires=[{"id": "A", "until": "read"}]), item("A", 2)]
    p = plan(items, sessions("A", 3, 60) + sessions("B", 1, 60))
    assert day_of(p, "A3", "read") == [3]
    assert day_of(p, "B1", "read") == [4]


def test_dependent_waits_for_all_reviews_when_asked():
    items = [item("A", 1, review_intervals=[1, 2]), item("B", 2, requires=[{"id": "A", "until": "finished"}])]
    p = plan(items, sessions("A", 1, 60) + sessions("B", 1, 60))
    assert day_of(p, "A1", "review") == [2, 4]
    assert day_of(p, "B1", "read") == [5]


def test_inactive_prerequisite_is_ignored():
    items = [item("A", 1, is_active=False), item("B", 2, requires=[{"id": "A", "until": "read"}])]
    p = plan(items, sessions("A", 2, 60) + sessions("B", 1, 60))
    assert day_of(p, "B1", "read") == [1]


def test_manual_move_ignores_dependency():
    items = [item("A", 1), item("B", 2, requires=[{"id": "A", "until": "read"}])]
    sess = sessions("A", 3, 60) + sessions("B", 1, 60, read_manual_date=d(1))
    assert day_of(plan(items, sess), "B1", "read") == [1]


# ---------------------------------------------------------------------------
# API: وابستگی
# ---------------------------------------------------------------------------

def test_dependency_through_api_and_waiting_label(client):
    add(client, "الف", count=2)
    state = add(client, "ب", count=1)
    a, b = item_named(state, "الف"), item_named(state, "ب")
    state = client.patch(f"/api/items/{b['id']}", json={"requires": [{"id": a["id"]}]}).get_json()
    b = item_named(state, "ب")
    assert b["requires"] == [{"id": a["id"], "until": "read"}]
    assert b["waiting_for"] == ["الف"]
    read_end = date.fromisoformat(item_named(state, "الف")["finish"]["read_end"])
    assert days_of(state, b["sessions"][0]["id"], "read") == [read_end + timedelta(days=1)]
    # حذف پیش‌نیاز، وابستگی را هم پاک می‌کند
    state = client.delete(f"/api/items/{a['id']}").get_json()
    assert item_named(state, "ب")["requires"] == []


def test_dependency_cycle_is_rejected(client):
    add(client, "الف", count=1)
    add(client, "ب", count=1)
    state = add(client, "ج", count=1)
    ids = {i["title"]: i["id"] for i in state["items"]}
    client.patch(f"/api/items/{ids['ب']}", json={"requires": [{"id": ids["الف"]}]})
    client.patch(f"/api/items/{ids['ج']}", json={"requires": [{"id": ids["ب"]}]})
    response = client.patch(f"/api/items/{ids['الف']}", json={"requires": [{"id": ids["ج"]}]})
    assert response.status_code == 400 and "دور" in response.get_json()["error"]
    assert client.patch(f"/api/items/{ids['الف']}", json={"requires": [{"id": ids["الف"]}]}).status_code == 400


# ---------------------------------------------------------------------------
# تعطیلی چندروزه
# ---------------------------------------------------------------------------

def test_vacation_range(client):
    state = add(client, "A", count=1)
    today = today_of(state)
    s1 = session_of(state, "A")["id"]
    body = {"start": today.isoformat(), "end": (today + timedelta(days=4)).isoformat(), "cap_minutes": 0}
    state = client.post("/api/days/range", json=body).get_json()
    assert days_of(state, s1, "read") == [today + timedelta(days=5)]
    state = client.post("/api/days/range", json={**body, "cap_minutes": None}).get_json()
    assert days_of(state, s1, "read") == [today]
    assert client.post("/api/days/range", json={"start": "2026-02-02", "end": "2026-02-01"}).status_code == 400


# ---------------------------------------------------------------------------
# یادداشت و بایگانی
# ---------------------------------------------------------------------------

def test_session_note_survives_ticks(client, tmp_path):
    client.patch("/api/settings", json={"export_folder": str(tmp_path / "out")})
    state = add(client, "A", count=1)
    s1 = session_of(state, "A")["id"]
    state = client.patch(f"/api/sessions/{s1}", json={"note": "نکتهٔ مهم"}).get_json()
    assert session_of(state, "A")["note"] == "نکتهٔ مهم"
    name = client.post("/api/export", json={"scope": "day"}).get_json()["name"]
    assert "نکتهٔ مهم" in (tmp_path / "out" / name).read_text(encoding="utf-8")
    state = done(client, s1, "read").get_json()
    assert session_of(state, "A")["note"] == "نکتهٔ مهم"


def test_archive_only_finished(client):
    state = add(client, "A", count=1)
    a = item_named(state, "A")
    assert client.post(f"/api/items/{a['id']}/archive", json={}).status_code == 400
    s1 = a["sessions"][0]["id"]
    done(client, s1, "read")
    for _ in range(4):
        done(client, s1, "review")
    state = client.post(f"/api/items/{a['id']}/archive", json={}).get_json()
    assert item_named(state, "A")["archived"] is True
    assert len(state["history"]) == 5
    state = client.post(f"/api/items/{a['id']}/archive", json={"archived": False}).get_json()
    assert item_named(state, "A")["archived"] is False


# ---------------------------------------------------------------------------
# افزودن گروهی و ساختار فایل
# ---------------------------------------------------------------------------

def test_bulk_add(client):
    text = "زبان، ۵، ۳۰\nریاضی, 3\n\nتاریخ"
    state = client.post("/api/items/bulk", json={"text": text}).get_json()
    assert [(i["title"], len(i["sessions"]), i["sessions"][0]["minutes"]) for i in state["items"]] == \
        [("زبان", 5, 30), ("ریاضی", 3, 60), ("تاریخ", 1, 60)]
    assert len({i["display_color"] for i in state["items"]}) == 3
    assert client.post("/api/items/bulk", json={"text": "الف، ب"}).status_code == 400
    assert client.post("/api/items/bulk", json={"text": "  "}).status_code == 400


def test_outline_from_markdown(tmp_path):
    note = tmp_path / "n.md"
    note.write_text("# یک\n## الف\n# دو\n", encoding="utf-8")
    outline = sources.file_outline(note)
    assert outline["unit"] == "heading"
    assert [(e["level"], e["title"]) for e in outline["entries"]] == [(1, "یک"), (2, "الف"), (1, "دو")]


def test_outline_pdf_without_bookmarks_is_none(tmp_path):
    doc = pdfium.PdfDocument.new()
    doc.new_page(100, 100)
    buffer = io.BytesIO()
    doc.save(buffer)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(buffer.getvalue())
    assert sources.file_outline(pdf) is None


def test_create_sessions_from_sections(client):
    state = add(client, "کتاب", section_unit="page", sections=[
        {"title": "فصل ۱", "start": "1", "end": "20"}, {"title": "فصل ۲", "start": "21", "end": "40"}])
    sess = item_named(state, "کتاب")["sessions"]
    assert [(s["section_start"], s["section_end"]) for s in sess] == [("1", "20"), ("21", "40")]


def test_resplit_from_sections_keeps_read_sessions(client):
    state = add(client, "نوت", count=3, minutes=30)
    a = item_named(state, "نوت")
    done(client, a["sessions"][0]["id"], "read")
    state = client.post(f"/api/items/{a['id']}/split", json={
        "section_unit": "heading", "sections": [{"title": "یک", "start": "یک", "end": "یک"}]}).get_json()
    sess = item_named(state, "نوت")["sessions"]
    assert len(sess) == 2 and sess[0]["status"] == "reviewing" and sess[1]["section_start"] == "یک"


# ---------------------------------------------------------------------------
# الگو
# ---------------------------------------------------------------------------

def test_templates_saved_in_settings(client):
    templates = [{"name": "کتاب", "fields": {"session_count": 10, "session_minutes": 60, "hack": 1}}]
    state = client.patch("/api/settings", json={"item_templates": templates}).get_json()
    assert state["settings"]["item_templates"] == [
        {"name": "کتاب", "kind": "study", "fields": {"session_count": 10, "session_minutes": 60}}]
    assert client.patch("/api/settings", json={"item_templates": [{"name": ""}]}).status_code == 400


# ---------------------------------------------------------------------------
# آمار و گزارش
# ---------------------------------------------------------------------------

def test_stats_and_weekly_report(client, tmp_path):
    client.patch("/api/settings", json={"export_folder": str(tmp_path / "out")})
    client.post("/api/categories", json={"name": "زبان"})
    state = client.get("/api/state").get_json()
    state = add(client, "A", count=2, minutes=60, category_id=state["categories"][0]["id"])
    s1 = session_of(state, "A")["id"]
    done(client, s1, "read")
    done(client, s1, "review")
    data = client.get("/api/stats").get_json()
    assert data["days"] == [{"date": state["today"], "read": 60, "review": 20, "routine": 0}]
    assert len(data["weeks"]) == 12 and data["weeks"][-1]["read"] == 60
    assert data["categories"] == [{"name": "زبان", "total": 120, "read": 60, "items": 1}]
    w = data["summary"]
    assert w["period"] == "week" and w["length"] == 7
    assert w["done_count"] == 2 and w["active_days"] == 1
    assert w["courses"][0]["title"] == "A" and w["totals"]["review"] == 20
    name = client.post("/api/export/report", json={}).get_json()["name"]
    html = (tmp_path / "out" / name).read_text(encoding="utf-8")
    assert "گزارش هفته" in html and "<td>A</td>" in html
    month = client.get("/api/stats?period=month").get_json()
    assert month["summary"]["done_count"] == 2 and len(month["months"]) == 12
    assert month["months"][-1]["read"] == 60
    overall = client.get("/api/stats?period=all").get_json()["summary"]
    assert overall["start"] == state["today"] and overall["totals"]["read"] == 60
    assert overall["next_minutes"] > 0
    for period, text in (("month", "گزارش ماه"), ("all", "گزارش کلی")):
        name = client.post("/api/export/report", json={"period": period}).get_json()["name"]
        assert text in (tmp_path / "out" / name).read_text(encoding="utf-8")
    assert client.get("/api/stats?period=year").status_code == 400


# ---------------------------------------------------------------------------
# backup و انتقال
# ---------------------------------------------------------------------------

def test_restore_backup(client, tmp_path):
    client.get("/")   # backup امروز، با دیتابیس خالی
    add(client, "A", count=1)
    backups = client.get("/api/backups").get_json()
    assert len(backups) == 1
    state = client.post("/api/backups/restore", json={"name": backups[0]["name"]}).get_json()
    assert state["items"] == []
    assert any(b["safety"] for b in client.get("/api/backups").get_json())   # کپی ایمنی
    state = client.post("/api/undo", json={}).get_json()
    assert [i["title"] for i in state["items"]] == ["A"]
    assert client.post("/api/backups/restore", json={"name": "../../x"}).status_code == 400


def test_export_and_import_data(client, tmp_path, monkeypatch):
    monkeypatch.setattr(database, "FONTS_DIR", tmp_path / "fonts")
    (tmp_path / "fonts").mkdir()
    (tmp_path / "fonts" / "Test.ttf").write_bytes(b"font")
    client.patch("/api/settings", json={"export_folder": str(tmp_path / "out")})
    add(client, "A", count=1)
    result = client.post("/api/data/export", json={}).get_json()
    assert result["name"].endswith(".zip")
    zip_path = tmp_path / "out" / result["name"]
    assert set(zipfile.ZipFile(zip_path).namelist()) == {"dibacheh.sqlite3", "fonts/Test.ttf"}
    add(client, "B", count=1)
    (tmp_path / "fonts" / "Test.ttf").unlink()
    monkeypatch.setattr(sources, "browse", lambda *a, **k: str(zip_path))
    state = client.post("/api/data/import", json={}).get_json()
    assert [i["title"] for i in state["items"]] == ["A"]
    assert (tmp_path / "fonts" / "Test.ttf").exists()


def test_import_rejects_bad_files(client, tmp_path, monkeypatch):
    bad = tmp_path / "bad.zip"
    bad.write_text("not a zip")
    monkeypatch.setattr(sources, "browse", lambda *a, **k: str(bad))
    assert client.post("/api/data/import", json={}).status_code == 400
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("dibacheh.sqlite3", "not a database at all")
    assert client.post("/api/data/import", json={}).status_code == 400
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("other.txt", "x")
    assert client.post("/api/data/import", json={}).status_code == 400


def test_old_database_is_migrated_on_restore(conn, tmp_path):
    old = tmp_path / "old.sqlite3"
    c = sqlite3.connect(old)
    for n, script in enumerate(database.MIGRATIONS[:2], start=1):
        c.executescript(f"BEGIN; {script} PRAGMA user_version = {n}; COMMIT;")
    c.close()
    database.check_database_file(old)
    database.replace_database(conn, old)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(database.MIGRATIONS)
    conn.execute("SELECT archived FROM items")
