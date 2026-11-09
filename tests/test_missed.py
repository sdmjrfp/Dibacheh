"""کارهای انجام‌نشده: ماندن در تقویم، حذف، «انجام شد» و نمره."""

from datetime import date, datetime, timedelta

import database
import reports
from services import missed, tasks
from services import state as state_service

DAY1 = date(2026, 3, 2)
DAY2 = DAY1 + timedelta(days=1)
NOW = datetime(2026, 3, 2, 12, 0)


def state_on(conn, day):
    return state_service.state_data(conn, day, {})


def first_session(conn, item_id):
    return database.list_sessions(conn, item_id)[0]


def tasks_on(state, day):
    found = next((d for d in state["plan"]["days"] if d["date"] == day), None)
    return found["tasks"] if found else []


def test_unticked_lesson_stays_grey_and_moves_on(conn):
    item = database.add_item(conn, "A", 1, 60, now=NOW)
    state_on(conn, DAY1)
    state = state_on(conn, DAY2)
    assert [(m["date"], m["kind"]) for m in state["missed"]] == [(DAY1, "read")]
    assert [t["kind"] for t in tasks_on(state, DAY2)] == ["read"]
    assert state["missed"][0]["item_id"] == item


def test_ticked_task_is_not_missed(conn):
    item = database.add_item(conn, "A", 1, 60, now=NOW)
    state_on(conn, DAY1)
    tasks.mark_done(conn, {"session_id": first_session(conn, item)["id"], "kind": "read"}, DAY1)
    state_on(conn, DAY1)
    assert state_on(conn, DAY2)["missed"] == []


def test_postponed_task_is_not_missed(conn):
    item = database.add_item(conn, "A", 1, 60, now=NOW)
    state_on(conn, DAY1)
    tasks.move_task(conn, {"session_id": first_session(conn, item)["id"], "kind": "read", "date": DAY2.isoformat()}, DAY1)
    state_on(conn, DAY1)
    assert state_on(conn, DAY2)["missed"] == []


def test_routine_is_missed_but_does_not_move(conn):
    database.add_item(conn, "R", 3, 10, now=NOW, item_type="routine", start_date=DAY1)
    state_on(conn, DAY1)
    state = state_on(conn, DAY2)
    assert [m["kind"] for m in state["missed"]] == ["routine"]
    assert len(tasks_on(state, DAY2)) == 1   # فقط روتین خود امروز، نه دو تا


def test_app_closed_for_days_counts_each_planned_day(conn):
    item = database.add_item(conn, "A", 3, 60, now=NOW, max_new_sessions_per_day=1)
    state_on(conn, DAY1)
    state = state_on(conn, DAY1 + timedelta(days=3))
    assert [(m["date"], m["kind"]) for m in state["missed"]] == [
        (DAY1, "read"), (DAY1 + timedelta(days=1), "read"), (DAY1 + timedelta(days=2), "read")]
    assert item


def test_rolling_over_twice_does_not_duplicate(conn):
    database.add_item(conn, "A", 1, 60, now=NOW)
    state_on(conn, DAY1)
    state_on(conn, DAY2)
    assert len(state_on(conn, DAY2)["missed"]) == 1


def test_dismiss_changes_only_the_score_not_the_plan(conn):
    database.add_item(conn, "A", 1, 60, now=NOW)
    state_on(conn, DAY1)
    state = state_on(conn, DAY2)
    plan_before = [(d["date"], len(d["tasks"])) for d in state["plan"]["days"]]
    missed.dismiss(conn, state["missed"][0]["id"])
    state = state_on(conn, DAY2)
    assert state["missed"] == []
    assert [(d["date"], len(d["tasks"])) for d in state["plan"]["days"]] == plan_before
    state = state_on(conn, DAY2 + timedelta(days=0))
    assert state["missed"] == []     # برنمی‌گردد


def test_mark_done_removes_from_future_plan_and_logs_on_that_day(conn):
    item = database.add_item(conn, "A", 1, 60, now=NOW)
    state_on(conn, DAY1)
    state = state_on(conn, DAY2)
    missed.mark_done(conn, state["missed"][0]["id"])
    state = state_on(conn, DAY2)
    assert state["missed"] == []
    assert not [t for t in tasks_on(state, DAY2) if t["kind"] == "read"]
    session = first_session(conn, item)
    assert session["status"] == "reviewing" and session["read_at"] == DAY1
    assert [e["date"] for e in database.list_log(conn)] == [DAY1]
    # مرور اول از روز واقعی خواندن حساب می‌شود
    assert any(t["kind"] == "review" for t in tasks_on(state, DAY2))


def test_task_done_later_stays_missed_and_cannot_be_marked_again(conn):
    item = database.add_item(conn, "A", 1, 60, now=NOW)
    state_on(conn, DAY1)
    state_on(conn, DAY2)
    tasks.mark_done(conn, {"session_id": first_session(conn, item)["id"], "kind": "read"}, DAY2)
    state = state_on(conn, DAY2)
    assert len(state["missed"]) == 1 and state["missed"][0]["resolved"] is True


def test_routine_mark_done(conn):
    database.add_item(conn, "R", 3, 10, now=NOW, item_type="routine", start_date=DAY1)
    state_on(conn, DAY1)
    state = state_on(conn, DAY2)
    missed.mark_done(conn, state["missed"][0]["id"])
    assert state_on(conn, DAY2)["missed"] == []
    assert database.list_log(conn)[0]["task_type"] == "routine"


def test_score_counts_done_and_missed_per_item(conn):
    a = database.add_item(conn, "A", 2, 30, now=NOW, max_new_sessions_per_day=2)
    database.add_item(conn, "B", 1, 30, now=NOW)
    state_on(conn, DAY1)
    tasks.mark_done(conn, {"session_id": first_session(conn, a)["id"], "kind": "read"}, DAY1)
    state_on(conn, DAY1)
    state = state_on(conn, DAY2)
    summary = reports.summary(conn, state, "week", DAY1)
    score = summary["score"]
    assert score["done"] == 1 and score["missed"] == 2
    assert score["total"] == 33 and score["band"] == "red"
    by_title = {i["title"]: i for i in score["items"]}
    assert by_title["A"]["done"] == 1 and by_title["A"]["missed"] == 1
    assert by_title["B"]["total"] == 0


def test_routes_and_undo(client):
    # مسیرها: شمارهٔ نامعتبر پیدا نمی‌شود
    assert client.delete("/api/missed/999").status_code == 404
    assert client.post("/api/missed/999/done", json={}).status_code == 404
