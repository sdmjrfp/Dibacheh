"""تست‌های تغییرات دستی از داخل تقویم و برگرداندن تغییرها."""

from datetime import date, timedelta

import app as app_module
from test_api import add, item_named


def days_of(state, session_id, kind):
    """روزهایی (به شکل date) که یک کار از یک جلسه در برنامه آمده است."""
    return [date.fromisoformat(d["date"]) for d in state["plan"]["days"]
            for t in d["tasks"] if t["session_id"] == session_id and t["kind"] == kind]


def today_of(state):
    return date.fromisoformat(state["today"])


def move(client, session_id, kind, day):
    return client.post("/api/tasks/move", json={
        "session_id": session_id, "kind": kind, "date": day.isoformat() if day else None})


def mark_reviewing(session_id, read_at):
    conn = app_module.database.connect(app_module.app.config["DB_PATH"])
    app_module.database.update_session(conn, session_id, status="reviewing", leitner_box=1,
                                       minutes_done=60, read_at=read_at)
    conn.close()


def test_move_reading_later_shifts_its_reviews(client):
    state = add(client, "A", count=2)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    today = today_of(state)
    state = move(client, s1, "read", today + timedelta(days=3)).get_json()
    assert days_of(state, s1, "read") == [today + timedelta(days=3)]
    assert days_of(state, s1, "review")[0] == today + timedelta(days=4)
    task = next(t for d in state["plan"]["days"] for t in d["tasks"] if t["session_id"] == s1)
    assert task["manual"] is True


def test_postpone_then_back_to_automatic(client):
    state = add(client, "A", count=1)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    today = today_of(state)
    move(client, s1, "read", today + timedelta(days=1))
    state = move(client, s1, "read", None).get_json()
    assert days_of(state, s1, "read") == [today]


def test_bring_future_session_to_today(client):
    state = add(client, "A", count=3)
    s3 = item_named(state, "A")["sessions"][2]["id"]
    today = today_of(state)
    assert days_of(state, s3, "read") == [today + timedelta(days=2)]
    state = move(client, s3, "read", today).get_json()
    assert days_of(state, s3, "read") == [today]


def test_move_review_shifts_following_reviews(client):
    state = add(client, "A", count=1)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    today = today_of(state)
    mark_reviewing(s1, today - timedelta(days=1))          # مرور اول امروز است
    state = client.get("/api/state").get_json()
    assert days_of(state, s1, "review")[:2] == [today, today + timedelta(days=3)]
    state = move(client, s1, "review", today + timedelta(days=2)).get_json()
    assert days_of(state, s1, "review")[:2] == [today + timedelta(days=2), today + timedelta(days=5)]


def test_review_cannot_go_before_reading(client):
    state = add(client, "A", count=1)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    today = today_of(state)
    mark_reviewing(s1, today)
    response = move(client, s1, "review", today)
    assert response.status_code == 400


def test_review_of_unread_session_cannot_be_moved(client):
    state = add(client, "A", count=1)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    response = move(client, s1, "review", today_of(state) + timedelta(days=5))
    assert response.status_code == 400
    assert "خواندنش را جابه‌جا کنید" in response.get_json()["error"]


def test_cannot_move_to_the_past(client):
    state = add(client, "A", count=1)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    assert move(client, s1, "read", today_of(state) - timedelta(days=1)).status_code == 400


def test_day_off_and_cap(client):
    state = add(client, "A", count=2)
    today = today_of(state)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    state = client.put(f"/api/days/{today.isoformat()}", json={"cap_minutes": 0}).get_json()
    assert state["plan"]["days"][0]["is_off"]
    assert days_of(state, s1, "read") == [today + timedelta(days=1)]
    state = client.put(f"/api/days/{today.isoformat()}", json={"cap_minutes": None}).get_json()
    assert days_of(state, s1, "read") == [today]
    state = client.put(f"/api/days/{today.isoformat()}", json={"cap_minutes": 300}).get_json()
    assert state["plan"]["days"][0]["cap"] == 300


def test_new_item_from_a_calendar_day(client):
    state = client.get("/api/state").get_json()
    day = today_of(state) + timedelta(days=4)
    state = add(client, "A", count=2, first_date=day.isoformat())
    sessions = item_named(state, "A")["sessions"]
    assert days_of(state, sessions[0]["id"], "read") == [day]
    assert days_of(state, sessions[1]["id"], "read")[0] > day
    state = add(client, "ورزش", count=2, minutes=10, item_type="routine", first_date=day.isoformat())
    assert item_named(state, "ورزش")["start_date"] == day.isoformat()


# ---------------------------------------------------------------------------
# برگرداندن
# ---------------------------------------------------------------------------

def test_undo_several_steps(client):
    add(client, "A")
    state = add(client, "B")
    assert state["undo"] == {"count": 2, "label": "افزودن درس"}
    b = item_named(state, "B")["id"]
    client.delete(f"/api/items/{b}")
    state = client.post("/api/undo", json={}).get_json()        # حذف B برگشت
    assert state["undone"] == "حذف درس"
    assert [i["title"] for i in state["items"]] == ["A", "B"]
    state = client.post("/api/undo", json={}).get_json()        # افزودن B برگشت
    assert [i["title"] for i in state["items"]] == ["A"]
    assert state["undo"]["count"] == 1


def test_failed_change_is_not_in_undo(client):
    add(client, "A")
    client.post("/api/items", json={"title": "", "session_count": 1, "session_minutes": 10})
    state = client.get("/api/state").get_json()
    assert state["undo"]["count"] == 1


def test_undo_with_nothing_to_undo(client):
    assert client.post("/api/undo", json={}).status_code == 400


def test_undo_keeps_only_last_20(client):
    for n in range(25):
        add(client, f"درس {n}", count=1)
    state = client.get("/api/state").get_json()
    assert state["undo"]["count"] == 20
