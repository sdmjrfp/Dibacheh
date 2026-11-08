"""تست‌های تیک، پیشرفت جزئی، نشانگر حجم کار و تاریخ هدف."""

from datetime import date, timedelta

from test_api import add, item_named
from test_calendar_api import days_of, today_of


def done(client, session_id, kind, result="done", minutes=None):
    body = {"session_id": session_id, "kind": kind, "result": result}
    if minutes is not None:
        body["minutes"] = minutes
    return client.post("/api/tasks/done", json=body)


def session_of(state, title, n=0):
    return item_named(state, title)["sessions"][n]


def test_tick_reading_starts_reviews_and_logs(client):
    state = add(client, "A", count=2)
    s1 = session_of(state, "A")["id"]
    today = today_of(state)
    state = done(client, s1, "read").get_json()
    s = session_of(state, "A")
    assert (s["status"], s["leitner_box"], s["read_at"]) == ("reviewing", 1, today.isoformat())
    assert days_of(state, s1, "read") == []
    assert days_of(state, s1, "review")[0] == today + timedelta(days=1)
    assert state["history"][-1]["task_type"] == "read"
    assert state["history"][-1]["date"] == today.isoformat()
    assert item_named(state, "A")["status_list"] == "reading"


def test_tick_does_not_pull_next_session_into_today(client):
    state = add(client, "A", count=3, minutes=60)
    s1, s2 = [s["id"] for s in item_named(state, "A")["sessions"][:2]]
    today = today_of(state)
    state = done(client, s1, "read").get_json()
    assert days_of(state, s2, "read") == [today + timedelta(days=1)]  # سرعت 1 جلسه در روز
    assert state["plan"]["days"][0]["done"] == 60


def test_tick_review_and_needs_more(client):
    state = add(client, "A", count=1)
    s1 = session_of(state, "A")["id"]
    today = today_of(state)
    done(client, s1, "read")
    state = done(client, s1, "review").get_json()       # مرور زودتر از موعد، امروز
    assert session_of(state, "A")["leitner_box"] == 2
    assert days_of(state, s1, "review")[0] == today + timedelta(days=3)
    state = done(client, s1, "review", "needs_more").get_json()
    assert session_of(state, "A")["leitner_box"] == 1
    assert days_of(state, s1, "review")[0] == today + timedelta(days=1)
    assert state["history"][-1]["result"] == "needs_more"


def test_full_cycle_finishes_item(client):
    state = add(client, "A", count=1)
    s1 = session_of(state, "A")["id"]
    done(client, s1, "read")
    for _ in range(4):
        state = done(client, s1, "review").get_json()
    assert item_named(state, "A")["status_list"] == "finished"
    assert item_named(state, "A")["progress"] == {"read_percent": 100, "reviews_done": 4, "reviews_total": 4}
    assert done(client, s1, "review").status_code == 400


def test_partial_reading(client):
    state = add(client, "A", count=1, minutes=60)
    s1 = session_of(state, "A")["id"]
    today = today_of(state)
    state = done(client, s1, "read", "partial", 20).get_json()
    s = session_of(state, "A")
    assert (s["status"], s["minutes_done"]) == ("reading", 20)
    task = next(t for d in state["plan"]["days"] for t in d["tasks"] if t["session_id"] == s1)
    assert task["minutes"] == 40 and task["partial"]
    assert days_of(state, s1, "read") == [today + timedelta(days=1)]   # بقیه از فردا
    assert days_of(state, s1, "review") and days_of(state, s1, "review")[0] > today + timedelta(days=1)
    assert item_named(state, "A")["progress"]["read_percent"] == 33
    # بقیه هم خوانده شد
    state = done(client, s1, "read", "partial", 40).get_json()
    assert session_of(state, "A")["status"] == "reviewing"
    assert [h["minutes"] for h in state["history"]] == [20, 40]


def test_tick_routine(client):
    state = add(client, "ورزش", count=3, minutes=10, item_type="routine")
    w1 = session_of(state, "ورزش")["id"]
    state = done(client, w1, "routine").get_json()
    assert session_of(state, "ورزش")["status"] == "finished"
    assert days_of(state, w1, "routine") == []
    assert state["history"][-1]["task_type"] == "routine"


def test_tick_can_be_undone(client):
    state = add(client, "A", count=1)
    s1 = session_of(state, "A")["id"]
    done(client, s1, "read")
    state = client.post("/api/undo", json={}).get_json()
    assert state["undone"] == "ثبت انجام کار"
    assert session_of(state, "A")["status"] == "unread"
    assert state["history"] == []


def test_workload(client):
    state = add(client, "A", count=3, minutes=60)
    w = state["workload"]
    assert w["read_minutes"] == 180
    assert w["review_minutes"] == 3 * 4 * 20
    assert w["avg_read_next_30"] == 6          # 180 دقیقه در 30 روز
    assert w["end_date"] is not None


def test_target_status_read_and_review_separately(client):
    state = client.get("/api/state").get_json()
    today = today_of(state)
    target = today + timedelta(days=10)
    state = add(client, "A", count=2, target_date=target.isoformat())
    t = item_named(state, "A")["target"]
    read_end = date.fromisoformat(item_named(state, "A")["finish"]["read_end"])
    review_end = date.fromisoformat(item_named(state, "A")["finish"]["review_end"])
    assert t["read"] == {"done": False, "days": (target - read_end).days}
    assert t["review"]["days"] == (target - review_end).days
    assert t["read"]["days"] > 0 > t["review"]["days"]   # خواندن جلوتر، مرور عقب‌تر از هدف


# ---------------------------------------------------------------------------
# انجام‌نشده کردن کار
# ---------------------------------------------------------------------------

def undone(client, log_id):
    return client.post("/api/tasks/undone", json={"log_id": log_id})


def test_undone_reading_returns_session_to_plan(client):
    state = add(client, "A", count=1)
    s1 = session_of(state, "A")["id"]
    today = today_of(state)
    state = done(client, s1, "read").get_json()
    state = undone(client, state["history"][-1]["id"]).get_json()
    s = session_of(state, "A")
    assert (s["status"], s["leitner_box"], s["read_at"], s["minutes_done"]) == ("unread", 0, None, 0)
    assert state["history"] == []
    assert days_of(state, s1, "read") == [today]


def test_undone_review_restores_box(client):
    state = add(client, "A", count=1)
    s1 = session_of(state, "A")["id"]
    done(client, s1, "read")
    done(client, s1, "review")
    state = done(client, s1, "review", "needs_more").get_json()
    assert session_of(state, "A")["leitner_box"] == 1
    state = undone(client, state["history"][-1]["id"]).get_json()
    assert session_of(state, "A")["leitner_box"] == 2


def test_only_latest_tick_of_a_session_can_be_undone(client):
    state = add(client, "A", count=1)
    s1 = session_of(state, "A")["id"]
    done(client, s1, "read")
    state = done(client, s1, "review").get_json()
    response = undone(client, state["history"][0]["id"])
    assert response.status_code == 400
    state = undone(client, state["history"][1]["id"]).get_json()
    state = undone(client, state["history"][0]["id"]).get_json()
    assert session_of(state, "A")["status"] == "unread"


def test_undone_partial_and_routine(client):
    state = add(client, "A", count=1, minutes=60)
    s1 = session_of(state, "A")["id"]
    state = done(client, s1, "read", "partial", 20).get_json()
    state = undone(client, state["history"][-1]["id"]).get_json()
    s = session_of(state, "A")
    assert (s["status"], s["minutes_done"], s["read_manual_date"]) == ("unread", 0, None)
    state = add(client, "ورزش", count=2, minutes=10, item_type="routine")
    w1 = session_of(state, "ورزش")["id"]
    state = done(client, w1, "routine").get_json()
    state = undone(client, state["history"][-1]["id"]).get_json()
    assert session_of(state, "ورزش")["status"] == "unread"
    assert days_of(state, w1, "routine") == [today_of(state)]


def test_undone_old_tick_without_saved_state(client):
    """تیک‌هایی که قبل از این قابلیت ثبت شده‌اند هم برمی‌گردند."""
    import app as app_module
    import database
    state = add(client, "A", count=1)
    s1 = session_of(state, "A")["id"]
    done(client, s1, "read")
    state = done(client, s1, "review").get_json()
    conn = database.connect(app_module.app.config["DB_PATH"])
    conn.execute("UPDATE task_log SET before_state = NULL")
    conn.commit()
    conn.close()
    state = undone(client, state["history"][-1]["id"]).get_json()
    s = session_of(state, "A")
    assert (s["status"], s["leitner_box"], s["read_at"]) == ("reviewing", 1, state["today"])


def test_reset_course_blocks_undoing_old_ticks(client):
    state = add(client, "A", count=1)
    item_id = item_named(state, "A")["id"]
    state = done(client, session_of(state, "A")["id"], "read").get_json()
    client.post(f"/api/items/{item_id}/reset", json={})
    assert undone(client, state["history"][-1]["id"]).status_code == 400
