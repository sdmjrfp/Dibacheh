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


def test_new_sources_get_different_colors_and_can_change(client):
    add(client, "الف", count=1)
    state = add(client, "ب", count=1)
    a, b = item_named(state, "الف"), item_named(state, "ب")
    assert a["display_color"] != b["display_color"]
    state = client.patch(f"/api/items/{a['id']}", json={"color": "#123456"}).get_json()
    assert item_named(state, "الف")["display_color"] == "#123456"
    assert client.patch(f"/api/items/{a['id']}", json={"color": "red"}).status_code == 400


def test_color_mode_setting(client):
    state = client.patch("/api/settings", json={"color_mode": "source"}).get_json()
    assert state["settings"]["color_mode"] == "source"
    assert client.patch("/api/settings", json={"color_mode": "rainbow"}).status_code == 400


def test_export_uses_source_colors_and_bundled_font(client, tmp_path):
    client.patch("/api/settings", json={"color_mode": "source", "font_family": "Samim",
                                        "export_folder": str(tmp_path / "out")})
    state = add(client, "A", count=1, color="#123456")
    name = client.post("/api/export", json={"scope": "day"}).get_json()["name"]
    html = (tmp_path / "out" / name).read_text(encoding="utf-8")
    assert "#123456" in html
    assert 'font-family: "Samim"' in html


def test_bundled_fonts_exist_with_licenses(client):
    state = client.get("/api/state").get_json()
    root = Path(app_module.app.static_folder) / "vendor" / "fonts"
    assert len(state["bundled_fonts"]) >= 5
    for font in state["bundled_fonts"]:
        assert (root / font["regular"]).is_file()
        assert (root / font["regular"]).parent.joinpath("LICENSE.txt").is_file()
        if font["bold"]:
            assert (root / font["bold"]).is_file()
