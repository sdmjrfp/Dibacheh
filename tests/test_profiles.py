"""کاربران: جدا بودن داده‌ها، ورود، رمز و عکس."""

import base64
import json
from pathlib import Path

import pytest

import app as app_module
import database
import profiles

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0 tiny").decode()


def public(client):
    return client.get("/api/profiles").get_json()


def titles(client):
    return [i["title"] for i in client.get("/api/state").get_json()["items"]]


def add_item(client, title):
    assert client.post("/api/items", json={"title": title, "session_count": 1, "session_minutes": 30}).status_code == 200


def main_db():
    return Path(app_module.app.config["DB_PATH"])


def test_single_user_without_password_enters_directly(client):
    info = public(client)
    assert info["login_required"] is False and len(info["profiles"]) == 1
    assert client.get("/api/state").status_code == 200


def test_first_profile_is_the_existing_data_and_stays_in_place(client):
    add_item(client, "قدیمی")
    client.post("/api/profiles", json={"name": "علی", "avatar": "a2"})
    assert titles(client) == []
    # بازگشت به کاربر اول: داده همان جاست
    client.post("/api/profiles/login", json={"id": "main"})
    assert titles(client) == ["قدیمی"]
    assert main_db().is_file()


def test_each_user_has_separate_data_paths_and_undo(client):
    add_item(client, "الف")
    assert client.get("/api/state").get_json()["undo"]["count"] == 1
    client.post("/api/profiles", json={"name": "Sara Lee", "avatar": "a3"})
    state = client.get("/api/state").get_json()
    assert state["undo"]["count"] == 0
    settings = state["settings"]
    assert "Sara-Lee" in settings["export_folder"] and "Sara-Lee" in settings["backup_folder"]
    assert database.FONTS_DIR != profiles._originals["fonts"]
    add_item(client, "ب")
    assert titles(client) == ["ب"]
    new_id = public(client)["active"]
    folder = next(p for p in json.loads((main_db().parent / "profiles.json").read_text(encoding="utf-8"))["profiles"] if p["id"] == new_id)["folder"]
    assert "Sara-Lee" in folder and (main_db().parent / folder / "dibacheh.sqlite3").is_file()
    client.post("/api/profiles/login", json={"id": "main"})
    assert titles(client) == ["الف"]


def test_new_user_inherits_language_and_skips_setup(client):
    client.patch("/api/settings", json={"language": "de", "calendar": "gregorian", "first_weekday": 0})
    client.post("/api/profiles", json={"name": "Anna", "avatar": "a1"})
    settings = client.get("/api/state").get_json()["settings"]
    assert (settings["language"], settings["calendar"], settings["setup_done"]) == ("de", "gregorian", True)


def restart():
    """مثل بستن و باز کردن برنامه: کسی وارد نشده است."""
    profiles._active.clear()
    profiles._last.clear()


def test_two_users_need_login_after_restart(client):
    client.post("/api/profiles", json={"name": "علی", "avatar": "a2"})
    restart()
    info = public(client)
    assert info["login_required"] is True and info["active"] is None
    response = client.get("/api/state")
    assert response.status_code == 401 and response.get_json()["login_required"] is True
    assert client.post("/api/items", json={"title": "x"}).status_code == 401
    assert client.get("/").status_code == 200       # صفحهٔ ورود باز می‌شود
    assert client.post("/api/profiles/login", json={"id": "main"}).status_code == 200
    assert client.get("/api/state").status_code == 200


def test_single_user_with_password_needs_login(client):
    client.patch("/api/profiles/main", json={"password": "رمز۱"})
    restart()
    assert public(client)["login_required"] is True
    response = client.post("/api/profiles/login", json={"id": "main", "password": "غلط"})
    assert response.status_code == 400
    assert public(client)["login_required"] is True
    assert client.post("/api/profiles/login", json={"id": "main", "password": "رمز۱"}).status_code == 200
    assert public(client)["login_required"] is False


def test_switching_to_user_with_password_needs_it(client):
    client.post("/api/profiles", json={"name": "علی", "avatar": "a2", "password": "abc"})
    target = public(client)["active"]
    client.post("/api/profiles/login", json={"id": "main"})
    assert client.post("/api/profiles/login", json={"id": target}).status_code == 400
    assert public(client)["active"] == "main"
    assert client.post("/api/profiles/login", json={"id": target, "password": "abc"}).status_code == 200


def test_password_is_hashed_and_not_in_public_data_or_backups(client):
    client.patch("/api/profiles/main", json={"password": "very-secret"})
    raw = (main_db().parent / "profiles.json").read_text(encoding="utf-8")
    assert "very-secret" not in raw
    assert "hash" not in json.dumps(public(client)) and "salt" not in json.dumps(public(client))
    assert public(client)["profiles"][0]["has_password"] is True
    assert b"very-secret" not in main_db().read_bytes()


def test_remove_password(client):
    client.patch("/api/profiles/main", json={"password": "abc"})
    client.patch("/api/profiles/main", json={"password": ""})
    restart()
    assert public(client)["login_required"] is False


def test_cannot_edit_another_users_profile(client):
    client.post("/api/profiles", json={"name": "علی", "avatar": "a2", "password": "abc"})
    assert client.patch("/api/profiles/main", json={"name": "هک"}).status_code == 400
    target = public(client)["active"]
    client.post("/api/profiles/login", json={"id": "main"})
    assert client.patch(f"/api/profiles/{target}", json={"password": ""}).status_code == 400


@pytest.mark.parametrize("bad", [{"name": ""}, {"name": "x" * 41}, {"avatar": "a13"}, {"avatar": "../x"}])
def test_invalid_profile_values(client, bad):
    assert client.patch("/api/profiles/main", json=bad).status_code == 400


def test_duplicate_name_is_rejected(client):
    client.patch("/api/profiles/main", json={"name": "علی"})
    assert client.post("/api/profiles", json={"name": "علی", "avatar": "a1"}).status_code == 400


def test_folder_name_cannot_escape(client):
    client.post("/api/profiles", json={"name": "../../evil", "avatar": "a1"})
    data = json.loads((main_db().parent / "profiles.json").read_text(encoding="utf-8"))
    assert ".." not in data["profiles"][-1]["folder"] and data["profiles"][-1]["folder"].startswith("profiles/")


def test_photo_upload_serve_and_remove(client):
    assert client.get("/api/profiles/main/photo").status_code == 404
    assert client.patch("/api/profiles/main", json={"photo": JPEG}).status_code == 200
    response = client.get("/api/profiles/main/photo")
    assert response.status_code == 200 and response.data.startswith(b"\xff\xd8")
    assert public(client)["profiles"][0]["has_photo"] is True
    client.patch("/api/profiles/main", json={"remove_photo": True})
    assert client.get("/api/profiles/main/photo").status_code == 404


def test_only_real_jpeg_is_accepted_as_photo(client):
    fake = "data:image/jpeg;base64," + base64.b64encode(b"<script>").decode()
    assert client.patch("/api/profiles/main", json={"photo": fake}).status_code == 400
    assert client.patch("/api/profiles/main", json={"photo": "not base64!!"}).status_code == 400


def test_delete_moves_data_aside_and_main_cannot_be_deleted(client):
    client.post("/api/profiles", json={"name": "علی", "avatar": "a2"})
    target = public(client)["active"]
    add_item(client, "نگه‌داشتنی")
    assert client.delete(f"/api/profiles/{target}").status_code == 200
    kept = list((main_db().parent / "profiles-deleted").glob("*/dibacheh.sqlite3"))
    assert len(kept) == 1
    info = public(client)
    assert len(info["profiles"]) == 1 and info["active"] == "main"
    assert client.delete("/api/profiles/main").status_code == 400


def test_forgot_password_recovery_with_backup_file(client, tmp_path):
    """کاربر رمزدار داده دارد؛ کاربر تازه backup او را بدون رمز برمی‌گرداند و مسیرهای خودش را نگه می‌دارد."""
    add_item(client, "کار مهم")
    client.patch("/api/profiles/main", json={"password": "فراموش‌شده"})
    backup = tmp_path / "old-backup.sqlite3"
    source = database.connect(main_db())
    target = __import__("sqlite3").connect(backup)
    source.backup(target)
    target.close()
    source.close()
    client.post("/api/profiles", json={"name": "تازه", "avatar": "a4"})
    settings_before = client.get("/api/state").get_json()["settings"]
    from unittest import mock

    with mock.patch("sources.browse", return_value=str(backup)):
        assert client.post("/api/data/import", json={}).status_code == 200
    state = client.get("/api/state").get_json()
    assert [i["title"] for i in state["items"]] == ["کار مهم"]
    assert state["settings"]["backup_folder"] == settings_before["backup_folder"]
    assert state["settings"]["export_folder"] == settings_before["export_folder"]


def test_each_profile_has_its_own_cloud_folder(client):
    client.post("/api/profiles", json={"name": "علی", "avatar": "a2"})
    assert database.CLOUD_SUBFOLDER != profiles._originals["cloud"] and "علی" in database.CLOUD_SUBFOLDER
    client.post("/api/profiles/login", json={"id": "main"})
    assert database.CLOUD_SUBFOLDER == profiles._originals["cloud"]


def test_new_user_can_be_created_from_login_screen_when_password_is_forgotten(client):
    add_item(client, "قدیمی")
    client.patch("/api/profiles/main", json={"password": "فراموش‌شده"})
    restart()
    assert public(client)["login_required"] is True
    response = client.post("/api/profiles", json={"name": "تازه", "avatar": "a2"})
    assert response.status_code == 200
    info = public(client)
    assert info["login_required"] is False and info["active"] != "main"
    assert titles(client) == []     # دادهٔ کاربر رمزدار نشان داده نمی‌شود
