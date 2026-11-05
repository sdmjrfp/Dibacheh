"""تست‌های نوع کار ساخت کاربر، دسته‌ها، رنگ‌ها و فونت‌های اضافه‌شده."""

import shutil
from pathlib import Path

import pytest

import app as app_module
import database
from test_api import add, item_named


def test_custom_type_behaves_like_study(client):
    state = client.post("/api/types", json={"name": "پروژه", "behavior": "study", "color": "#8b5cf6"}).get_json()
    t = state["types"][0]
    state = add(client, "سایت", count=2, custom_type_id=t["id"])
    item = item_named(state, "سایت")
    assert (item["item_type"], item["custom_type_id"]) == ("study", t["id"])
    kinds = {task["kind"] for d in state["plan"]["days"] for task in d["tasks"]}
    assert kinds == {"read", "review"}


def test_custom_type_behaves_like_routine(client):
    state = client.post("/api/types", json={"name": "مدیتیشن", "behavior": "routine", "color": "#10b981"}).get_json()
    state = add(client, "صبح", count=3, minutes=10, custom_type_id=state["types"][0]["id"])
    kinds = {task["kind"] for d in state["plan"]["days"] for task in d["tasks"]}
    assert kinds == {"routine"}


def test_edit_and_delete_type_keeps_items(client):
    state = client.post("/api/types", json={"name": "پروژه", "behavior": "study", "color": "#8b5cf6"}).get_json()
    tid = state["types"][0]["id"]
    add(client, "سایت", count=1, custom_type_id=tid)
    state = client.patch(f"/api/types/{tid}", json={"name": "پروژهٔ بزرگ", "color": "#000000"}).get_json()
    assert (state["types"][0]["name"], state["types"][0]["color"]) == ("پروژهٔ بزرگ", "#000000")
    state = client.delete(f"/api/types/{tid}").get_json()
    item = item_named(state, "سایت")
    assert item["custom_type_id"] is None and item["item_type"] == "study"


def test_bad_type_values(client):
    assert client.post("/api/types", json={"name": "", "behavior": "study"}).status_code == 400
    assert client.post("/api/types", json={"name": "x", "behavior": "magic"}).status_code == 400
    assert client.post("/api/types", json={"name": "x", "color": "red"}).status_code == 400


def test_reorder_categories(client):
    client.post("/api/categories", json={"name": "الف"})
    state = client.post("/api/categories", json={"name": "ب"}).get_json()
    ids = [c["id"] for c in state["categories"]]
    state = client.post("/api/categories/reorder", json={"ids": ids[::-1]}).get_json()
    assert [c["name"] for c in state["categories"]] == ["ب", "الف"]


def test_colors_setting(client):
    state = client.patch("/api/settings", json={"colors": {"read": "#FF0000"}}).get_json()
    assert state["settings"]["colors"] == {"read": "#ff0000", "review": "#3b82f6", "routine": "#f5b400"}
    assert client.patch("/api/settings", json={"colors": {"read": "red"}}).status_code == 400


SYSTEM_FONT = next((p for p in [Path("/System/Library/Fonts/Supplemental/Tahoma.ttf"),
                                Path("/System/Library/Fonts/Supplemental/Arial.ttf")] if p.exists()), None)


@pytest.mark.skipif(SYSTEM_FONT is None, reason="فونت آزمایشی پیدا نشد")
def test_add_and_remove_font(client, tmp_path, monkeypatch):
    font = tmp_path / SYSTEM_FONT.name
    shutil.copy(SYSTEM_FONT, font)
    monkeypatch.setattr(database, "FONTS_DIR", tmp_path / "fonts")
    monkeypatch.setattr(app_module.sources, "browse", lambda *a, **k: str(font))
    state = client.post("/api/fonts/add", json={}).get_json()
    family = state["added_font"]
    assert state["settings"]["custom_fonts"] == [{"family": family, "file": font.name}]
    assert client.get(f"/fonts/{font.name}").status_code == 200
    assert client.get("/fonts/../app.py").status_code == 404
    client.patch("/api/settings", json={"font_family": family})
    state = client.post("/api/fonts/remove", json={"family": family}).get_json()
    assert state["settings"]["custom_fonts"] == []
    assert state["settings"]["font_family"] == "Vazirmatn"


def test_add_font_rejects_other_files(client, tmp_path, monkeypatch):
    other = tmp_path / "notes.txt"
    other.write_text("x")
    monkeypatch.setattr(app_module.sources, "browse", lambda *a, **k: str(other))
    assert client.post("/api/fonts/add", json={}).status_code == 400
