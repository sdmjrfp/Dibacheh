"""تست‌های بخش تنظیمات."""

from datetime import date, timedelta

from test_api import add, item_named
from test_calendar_api import days_of, today_of


def patch(client, **values):
    return client.patch("/api/settings", json=values)


def test_change_cap_rebuilds_plan(client):
    add(client, "A", count=4, minutes=60)
    state = patch(client, default_cap_minutes=240).get_json()
    assert state["plan"]["days"][0]["cap"] == 240
    s2 = item_named(state, "A")["sessions"][1]["id"]
    assert days_of(state, s2, "read") == [today_of(state) + timedelta(days=1)]  # سرعت هنوز 1 در روز


def test_weekday_caps_and_days_off(client):
    state = client.get("/api/state").get_json()
    weekday = today_of(state).weekday()
    state = patch(client, weekday_caps={str(weekday): 45}).get_json()
    assert state["plan"]["days"][0]["cap"] == 45
    state = patch(client, weekly_days_off=[weekday]).get_json()
    assert state["plan"]["days"][0]["is_off"]


def test_intervals_change_recalculates_reviews(client):
    state = add(client, "A", count=1)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    state = patch(client, review_intervals=[2, 10]).get_json()
    today = today_of(state)
    assert days_of(state, s1, "review") == [today + timedelta(days=2), today + timedelta(days=12)]


def test_invalid_values_are_rejected_and_nothing_saved(client):
    for bad in ({"review_intervals": [0, 3]}, {"review_intervals": []}, {"default_cap_minutes": -5},
                {"default_review_ratio": "abc"}, {"day_start_hour": 30}, {"theme": "pink"},
                {"font_family": 'x"; color: red'}, {"backup_retention": 0}, {"unknown": 1}):
        response = client.patch("/api/settings", json=bad)
        assert response.status_code == 400, bad
    # یک مقدار درست و یک مقدار غلط با هم: هیچ‌کدام ذخیره نمی‌شود
    assert patch(client, default_cap_minutes=200, review_intervals=[0]).status_code == 400
    state = client.get("/api/state").get_json()
    assert state["settings"]["default_cap_minutes"] == 120


def test_review_cap_percent_on_and_off(client):
    state = patch(client, review_cap_percent=40).get_json()
    assert state["settings"]["review_cap_percent"] == 40
    state = patch(client, review_cap_percent=None).get_json()
    assert state["settings"]["review_cap_percent"] is None


def test_new_item_defaults_are_used(client):
    patch(client, new_item_defaults={"session_minutes": 25, "max_new_sessions_per_day": 3, "category_id": None})
    state = client.post("/api/items", json={"title": "A", "session_count": 2}).get_json()
    a = item_named(state, "A")
    assert a["sessions"][0]["minutes"] == 25
    assert a["max_new_sessions_per_day"] == 3


def test_appearance_settings_are_saved(client):
    state = patch(client, theme="dark", font_family="B Nazanin", font_size=18).get_json()
    assert (state["settings"]["theme"], state["settings"]["font_family"], state["settings"]["font_size"]) == \
        ("dark", "B Nazanin", 18)

