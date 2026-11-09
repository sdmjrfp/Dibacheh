"""تست‌های بخش منابع درسی از راه API، مثل کاری که صفحه انجام می‌دهد."""

from datetime import date

import app as app_module
import config
import database
import platform_tools
import sources


def add(client, title="A", count=3, minutes=60, **extra):
    return client.post("/api/items", json={"title": title, "session_count": count,
                                           "session_minutes": minutes, **extra}).get_json()


def item_named(state, title):
    return next(i for i in state["items"] if i["title"] == title)


# ---------------------------------------------------------------------------
# امنیت
# ---------------------------------------------------------------------------

def test_change_without_csrf_token_is_rejected(client):
    response = client.post("/api/items", json={"title": "A"}, headers={"X-CSRF-Token": "wrong"})
    assert response.status_code == 403


def test_wrong_host_is_rejected(client):
    response = client.get("/api/state", headers={"Host": "evil.example:5000"})
    assert response.status_code == 403


def test_page_contains_csrf_token(client):
    assert config.CSRF_TOKEN in client.get("/").get_data(as_text=True)


def test_open_uses_only_registered_source(client, monkeypatch):
    calls = []
    monkeypatch.setattr(platform_tools.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    state = add(client, "L", source_type="url", source_path_or_url="https://youtu.be/abc")
    item_id = item_named(state, "L")["id"]
    # حتی اگر مرورگر آدرس دیگری بفرستد، فقط آدرس ثبت‌شده باز می‌شود
    client.post(f"/api/items/{item_id}/open", json={"path": "/etc/passwd"})
    assert calls == [platform_tools.open_args("https://youtu.be/abc")]


# ---------------------------------------------------------------------------
# افزودن، ویرایش، صف
# ---------------------------------------------------------------------------

def test_add_item_appears_in_plan(client):
    state = add(client, "A")
    a = item_named(state, "A")
    assert len(a["sessions"]) == 3
    assert a["status_list"] == "unread"
    assert a["finish"]["read_end"] == state["today"] or a["finish"]["read_end"] > state["today"]
    assert state["plan"]["days"][0]["tasks"][0]["kind"] == "read"


def test_empty_title_is_rejected(client):
    response = client.post("/api/items", json={"title": "  ", "session_count": 1, "session_minutes": 60})
    assert response.status_code == 400
    assert "عنوان" in response.get_json()["error"]


def test_reorder_changes_finish_dates_immediately(client):
    add(client, "A", count=3)
    state = add(client, "B", count=3)
    before = item_named(state, "B")["finish"]["read_end"]
    ids = [item_named(state, "B")["id"], item_named(state, "A")["id"]]
    state = client.post("/api/items/reorder", json={"ids": ids}).get_json()
    assert [i["title"] for i in state["items"]] == ["B", "A"]
    assert item_named(state, "B")["finish"]["read_end"] < before


def test_inactive_item_has_no_dates_and_no_tasks(client):
    state = add(client, "A")
    item_id = item_named(state, "A")["id"]
    state = client.patch(f"/api/items/{item_id}", json={"is_active": False}).get_json()
    assert item_named(state, "A")["finish"] == {"read_end": None, "review_end": None}
    assert all(not d["tasks"] for d in state["plan"]["days"])


def test_pdf_range_is_split_automatically(client):
    state = add(client, "کتاب", count=10, section_unit="page", range_start="1", range_end="150")
    sessions = item_named(state, "کتاب")["sessions"]
    assert sessions[0]["section_text"] == "صفحهٔ 1 تا 15"
    assert sessions[-1]["section_end"] == "150"
    assert item_named(state, "کتاب")["range_problems"] == []


def test_editing_a_session_range_shows_problems(client):
    state = add(client, "کتاب", count=2, section_unit="page", range_start="1", range_end="30")
    s1 = item_named(state, "کتاب")["sessions"][0]
    state = client.patch(f"/api/sessions/{s1['id']}", json={"section_end": "10"}).get_json()
    assert item_named(state, "کتاب")["range_problems"]


def test_resplit_keeps_read_sessions(client):
    state = add(client, "کتاب", count=4, section_unit="page", range_start="1", range_end="40")
    item = item_named(state, "کتاب")
    s1 = item["sessions"][0]
    conn = database.connect(app_module.app.config["DB_PATH"])
    database.update_session(conn, s1["id"], status="reviewing", leitner_box=2,
                                       minutes_done=60, read_at=date(2026, 1, 1))
    conn.close()
    state = client.post(f"/api/items/{item['id']}/split", json={"session_count": 2}).get_json()
    sessions = item_named(state, "کتاب")["sessions"]
    assert len(sessions) == 3
    assert sessions[0]["id"] == s1["id"] and sessions[0]["leitner_box"] == 2
    assert [(s["section_start"], s["section_end"]) for s in sessions[1:]] == [("11", "25"), ("26", "40")]
    assert [s["minutes"] for s in sessions[1:]] == [90, 90]


def test_review_override_on_session(client):
    state = add(client, "A", count=1)
    s = item_named(state, "A")["sessions"][0]
    state = client.patch(f"/api/sessions/{s['id']}", json={"review_minutes_override": 5}).get_json()
    reviews = [t for d in state["plan"]["days"] for t in d["tasks"] if t["kind"] == "review"]
    assert reviews and all(t["minutes"] == 5 for t in reviews)


def test_routine_with_weekdays(client):
    state = add(client, "ورزش", count=3, minutes=10, item_type="routine", routine_weekdays=[5])
    days = [d for d in state["plan"]["days"] if d["tasks"]]
    assert len(days) == 3
    assert all(date.fromisoformat(d["date"]).weekday() == 5 for d in days)


def test_delete_item(client):
    add(client, "A")
    state = add(client, "B")
    state = client.delete(f"/api/items/{item_named(state, 'A')['id']}").get_json()
    assert [i["title"] for i in state["items"]] == ["B"]


def test_reset_item_goes_to_end_of_queue(client):
    add(client, "A", count=1)
    state = add(client, "B", count=1)
    a = item_named(state, "A")
    conn = database.connect(app_module.app.config["DB_PATH"])
    database.update_session(conn, a["sessions"][0]["id"], status="finished", leitner_box=4)
    conn.close()
    state = client.get("/api/state").get_json()
    assert item_named(state, "A")["status_list"] == "finished"
    state = client.post(f"/api/items/{a['id']}/reset", json={}).get_json()
    assert item_named(state, "A")["status_list"] == "unread"
    assert [i["title"] for i in state["items"]] == ["B", "A"]


def test_categories(client):
    state = client.post("/api/categories", json={"name": "زبان"}).get_json()
    cat = state["categories"][0]
    state = add(client, "A", category_id=cat["id"])
    assert item_named(state, "A")["category_id"] == cat["id"]
    state = client.delete(f"/api/categories/{cat['id']}").get_json()
    assert item_named(state, "A")["category_id"] is None


def test_url_source_must_be_web_link(client):
    response = client.post("/api/items", json={"title": "L", "session_count": 1, "session_minutes": 10,
                                                "source_type": "url", "source_path_or_url": "file:///etc"})
    assert response.status_code == 400


def test_browse_cancel(client, monkeypatch):
    monkeypatch.setattr(sources, "browse", lambda *a, **k: None)
    assert client.post("/api/browse", json={"kind": "file"}).get_json() == {"cancelled": True}


def test_browse_inside_vault(client, monkeypatch, tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "n.md").write_text("x")
    client.patch("/api/settings", json={"vault_path": str(vault)})
    monkeypatch.setattr(sources, "browse", lambda *a, **k: str(vault / "n.md"))
    result = client.post("/api/browse", json={"kind": "file"}).get_json()
    assert result == {"source_type": "vault", "source_path_or_url": "n.md", "outline": None}


# ---------------------------------------------------------------------------
# حذف مرورهای یک درس
# ---------------------------------------------------------------------------

def plan_kinds(state, item_id):
    return {t["kind"] for d in state["plan"]["days"] for t in d["tasks"] if t["item_id"] == item_id}


def test_remove_reviews_removes_them_from_plan_and_finishes_reviewing_sessions(client):
    state = add(client, "A", count=2)
    item = item_named(state, "A")
    client.post("/api/tasks/done", json={"session_id": item["sessions"][0]["id"], "kind": "read", "result": "done"})
    state = client.delete(f"/api/items/{item['id']}/reviews").get_json()
    item = item_named(state, "A")
    assert plan_kinds(state, item["id"]) == {"read"}
    assert item["sessions"][0]["status"] == "finished"
    assert item["no_reviews"] is True
    assert item["progress"]["reviews_total"] == 0
    # سابقه می‌ماند
    assert len(state["history"]) == 1
    # جلسهٔ بعدی با خواندن تمام می‌شود
    state = client.post("/api/tasks/done", json={"session_id": item["sessions"][1]["id"], "kind": "read", "result": "done"}).get_json()
    assert item_named(state, "A")["status_list"] == "finished"


def test_remove_reviews_can_be_undone_and_restored(client):
    state = add(client, "A", count=1)
    item = item_named(state, "A")
    client.post("/api/tasks/done", json={"session_id": item["sessions"][0]["id"], "kind": "read", "result": "done"})
    client.delete(f"/api/items/{item['id']}/reviews")
    state = client.post("/api/undo", json={}).get_json()
    assert plan_kinds(state, item["id"]) == {"review"}
    client.delete(f"/api/items/{item['id']}/reviews")
    state = client.post(f"/api/items/{item['id']}/reviews", json={}).get_json()
    assert plan_kinds(state, item["id"]) == {"review"}
    assert item_named(state, "A")["sessions"][0]["status"] == "reviewing"


def test_routine_has_no_reviews_to_remove(client):
    state = add(client, "R", count=2, item_type="routine")
    response = client.delete(f"/api/items/{item_named(state, 'R')['id']}/reviews")
    assert response.status_code == 400


def test_undoing_tick_of_item_without_reviews_does_not_leave_it_reviewing(client):
    state = add(client, "A", count=1)
    item = item_named(state, "A")
    state = client.post("/api/tasks/done", json={"session_id": item["sessions"][0]["id"], "kind": "read", "result": "done"}).get_json()
    client.delete(f"/api/items/{item['id']}/reviews")
    state = client.post("/api/tasks/undone", json={"log_id": state["history"][-1]["id"]}).get_json()
    assert item_named(state, "A")["sessions"][0]["status"] == "unread"


# ---------------------------------------------------------------------------
# گونه‌های کار: پروژه و کار یک‌باره
# ---------------------------------------------------------------------------

def test_project_and_once_have_no_reviews(client):
    state = add(client, "P", count=3, variant="project")
    assert plan_kinds(state, item_named(state, "P")["id"]) == {"read"}
    state = add(client, "O", count=1, variant="once")
    assert item_named(state, "O")["no_reviews"] is True


def test_once_task_goes_to_chosen_day(client):
    state = client.get("/api/state").get_json()
    from datetime import date, timedelta
    day = (date.fromisoformat(state["today"]) + timedelta(days=5)).isoformat()
    state = add(client, "O", count=1, variant="once", first_date=day)
    days = [d["date"] for d in state["plan"]["days"] if d["tasks"]]
    assert days == [day]


def test_invalid_variant_is_rejected(client):
    assert client.post("/api/items", json={"title": "X", "variant": "exam"}).status_code == 400


def test_builtin_templates_are_listed_and_can_be_hidden(client):
    state = client.get("/api/state").get_json()
    ids = [t["id"] for t in state["templates"]]
    assert {"study-10", "study-30", "study-90"} <= set(ids)
    state = client.patch("/api/settings", json={"hidden_templates": ["study-10"]}).get_json()
    assert "study-10" not in [t["id"] for t in state["templates"]]


def test_own_template_keeps_kind_and_weekdays(client):
    template = {"name": "T", "kind": "routine", "fields": {"session_count": 3, "routine_weekdays": [1, 2]}}
    state = client.patch("/api/settings", json={"item_templates": [template]}).get_json()
    own = next(t for t in state["templates"] if t["name"] == "T")
    assert own["kind"] == "routine"
    assert own["fields"]["routine_weekdays"] == [1, 2]
