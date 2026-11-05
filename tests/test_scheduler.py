"""تست‌های پذیرش موتور چینش (بخش 13 سند).

شمارهٔ هر تست با شمارهٔ سناریو در PROJECT_SPEC.md یکی است.
"""

import time
from datetime import datetime, timedelta

import leitner
import scheduler
from helpers import DAY1, all_tasks, d, day_of, item, sessions, settings, table, totals


def build(items, sess, today=DAY1, overrides=None, **setting_changes):
    return scheduler.build_plan(items, sess, settings(**setting_changes), overrides or {}, today)


def base_input():
    """سناریوی پایه: A با 3 جلسهٔ 60 دقیقه‌ای، B با 2 جلسه."""
    items = [item("A", 1), item("B", 2)]
    sess = sessions("A", 3, 60) + sessions("B", 2, 60)
    return items, sess


def mark_read(sess, session_id, day, intervals=(1, 3, 7, 30)):
    """جلسه را در روز day خوانده‌شده علامت می‌زند."""
    return [leitner.finish_reading(s, day, list(intervals)) if s["id"] == session_id else s
            for s in sess]


# ---------------------------------------------------------------------------
# سناریوی پایه
# ---------------------------------------------------------------------------

def test_base_scenario():
    plan = build(*base_input())
    t = table(plan)
    assert t[1] == ["خواندن A1", "خواندن B1"]
    assert t[2] == ["مرور A1", "مرور B1", "خواندن A2"]
    assert t[3] == ["مرور A2", "خواندن A3", "خواندن B2"]
    assert t[4] == ["مرور A3", "مرور B2"]
    assert t[5] == ["مرور A1", "مرور B1"]
    tot = totals(plan)
    assert [tot[i] for i in range(1, 6)] == [120, 100, 140, 40, 40]


def test_1_missed_day_shifts_everything_by_one():
    base = table(build(*base_input()))
    shifted = table(build(*base_input(), today=d(2)), start=d(2))
    assert shifted == base


def test_2_day_off_loses_nothing():
    base = build(*base_input())
    off = build(*base_input(), overrides={d(3): 0})
    assert table(off)[3] == []
    assert off["days"][2]["is_off"]
    assert all_tasks(off) == all_tasks(base)
    # کارهای روز 3 بعد از آن آمده‌اند
    assert day_of(off, "A3", "read") == [4]


def test_3_higher_cap_on_day_2():
    plan = build(*base_input(), overrides={d(2): 200})
    t = table(plan)
    assert t[2] == ["مرور A1", "مرور B1", "خواندن A2", "خواندن B2"]
    # سرعت درس رعایت می‌شود: A3 روز 2 نمی‌آید
    assert day_of(plan, "A3", "read") == [3]


def test_4_reviews_before_new_material():
    # دو مرور 40 دقیقه‌ای موعدرسیده، سقف 60 بدون اضافه‌سقف
    items = [item("R", 1), item("N", 2)]
    sess = sessions("R", 2, 120) + sessions("N", 1, 20)
    sess = mark_read(sess, "R1", d(0))
    sess = mark_read(sess, "R2", d(0))
    plan = build(items, sess, default_cap_minutes=60, cap_tolerance_minutes=0)
    t = table(plan)
    # فقط یکی از مرورها جا می‌شود. با اینکه 20 دقیقه جا هست، مطلب جدید نمی‌آید.
    assert t[1] == ["مرور R1"]
    assert "خواندن N1" not in t[1]


def test_5_queue_order_for_new_sessions():
    items = [item("A", 1), item("B", 2), item("R", 0)]
    sess = sessions("A", 1, 60) + sessions("B", 1, 60) + sessions("R", 1, 60)
    sess = mark_read(sess, "R1", d(0))  # مرور 20 دقیقه‌ای امروز
    cfg = dict(default_cap_minutes=60, cap_tolerance_minutes=0)

    plan = build(items, sess, **cfg)
    assert table(plan)[1] == ["مرور R1"]  # درس جدید از مرور جلو نمی‌زند
    assert day_of(plan, "A1", "read") < day_of(plan, "B1", "read")

    items_b_first = [item("A", 2), item("B", 1), item("R", 0)]
    plan = build(items_b_first, sess, **cfg)
    assert table(plan)[1] == ["مرور R1"]
    assert day_of(plan, "B1", "read") < day_of(plan, "A1", "read")


def test_6_manual_move():
    items, sess = base_input()
    # A2 به‌طور عادی روز 2 است. دستی به روز 4 منتقل می‌شود.
    sess = [dict(s, read_manual_date=d(4)) if s["id"] == "A2" else s for s in sess]
    plan = build(items, sess)
    assert day_of(plan, "A2", "read") == [4]
    assert day_of(plan, "A2", "review")[0] == 5  # مرورها هم جابه‌جا می‌شوند
    assert day_of(plan, "A3", "read")[0] > 4    # جلسهٔ بعدی از A2 جلو نمی‌زند

    # روز 4 انجام نشد: از روز 5 برنامه ساخته می‌شود و A2 جلوتر می‌رود
    sess_after = mark_read(sess, "A1", d(1))
    sess_after = mark_read(sess_after, "B1", d(1))
    plan = build(items, sess_after, today=d(5))
    assert day_of(plan, "A2", "read") == [5]
    for r in day_of(plan, "A2", "review"):
        assert r > 5  # مرور هرگز قبل از خواندن نیست


def test_9_routine():
    items = [item("A", 1), item("B", 2),
             item("W", 0, item_type="routine", start_date=d(1))]
    sess = sessions("A", 3, 60) + sessions("B", 2, 60) + sessions("W", 3, 10)
    plan = build(items, sess)
    t = table(plan)
    assert t[1][0] == "روتین W1"     # قبل از بقیه
    assert t[2][0] == "روتین W2"     # قبل از مرورها
    assert totals(plan)[1] == 130     # از سقف کم می‌شود
    assert day_of(plan, "W1", "review") == []  # مرور ندارد

    # روز 1 ورزش انجام نشد: به روز 2 منتقل نمی‌شود
    plan = build(items, sess, today=d(2))
    t = table(plan)
    assert day_of(plan, "W1", "routine") == []
    assert t[2][0] == "روتین W2"
    assert t[3][0] == "روتین W3"
    assert not any(x.startswith("روتین") for x in t.get(4, []))


def test_9b_routine_day_off_is_burned():
    items = [item("W", 0, item_type="routine", start_date=d(1))]
    sess = sessions("W", 3, 10)
    plan = build(items, sess, overrides={d(2): 0})
    assert day_of(plan, "W2", "routine") == []
    assert day_of(plan, "W3", "routine") == [3]


def test_9c_routine_on_some_weekdays():
    # فقط شنبه (5) و دوشنبه (0). DAY1 شنبه است.
    items = [item("W", 0, item_type="routine", start_date=d(1), routine_weekdays=[5, 0])]
    plan = build(items, sessions("W", 3, 10))
    assert day_of(plan, "W1", "routine") == [1]   # شنبه
    assert day_of(plan, "W2", "routine") == [3]   # دوشنبه
    assert day_of(plan, "W3", "routine") == [8]   # شنبهٔ بعد


def test_9d_routine_future_start_date():
    items = [item("W", 0, item_type="routine", start_date=d(5))]
    plan = build(items, sessions("W", 2, 10))
    assert day_of(plan, "W1", "routine") == [5]
    assert day_of(plan, "W2", "routine") == [6]


def test_10_huge_session():
    items = [item("A", 1), item("H", 2), item("C", 3)]
    sess = sessions("A", 2, 60) + sessions("H", 1, 180) + sessions("C", 1, 30)
    plan = build(items, sess)
    # تقسیم نمی‌شود و در اولین روز بدون کار دیگر می‌آید
    assert day_of(plan, "H1", "read") == [4]
    assert table(plan)[4] == ["خواندن H1"]
    # جلوی صف را نمی‌گیرد: C که بعد از H است، روز 1 خوانده می‌شود
    assert day_of(plan, "C1", "read") == [1]


def test_10b_routine_counts_as_other_work_for_huge_session():
    items = [item("H", 1), item("W", 0, item_type="routine", start_date=d(1))]
    sess = sessions("H", 1, 180) + sessions("W", 2, 10)
    plan = build(items, sess)
    assert day_of(plan, "H1", "read") == [3]


def test_11_resplit_keeps_done_sessions():
    sess = sessions("A", 4, 60)
    sess = mark_read(sess, "A1", d(1))
    sess = [dict(s, leitner_box=3) if s["id"] == "A1" else s for s in sess]
    kept, new = scheduler.resplit_remaining(sess, 2)
    assert [s["id"] for s in kept] == ["A1"]
    assert kept[0]["leitner_box"] == 3
    assert [s["minutes"] for s in new] == [90, 90]  # 180 دقیقهٔ باقی‌مانده
    assert [s["sequence"] for s in new] == [2, 3]


def test_12_deterministic():
    items, sess = base_input()
    assert build(items, sess) == build(items, sess)


def test_13_overflow_tolerance():
    # X با 80 دقیقه روز را شروع می‌کند، 40 دقیقه جای خالی می‌ماند
    items = [item("X", 1), item("Y", 2)]
    plan = build(items, sessions("X", 1, 80) + sessions("Y", 1, 60))
    assert day_of(plan, "Y1", "read") == [1]      # 140 <= 150
    plan = build(items, sessions("X", 1, 80) + sessions("Y", 1, 75))
    assert day_of(plan, "Y1", "read") == [2]      # 155 > 150


def test_smaller_task_may_jump_ahead():
    # تصمیم کاربر: اگر کار جلوی صف جا نشد، کار کوچک‌تر بعدی می‌تواند بیاید
    items = [item("X", 1), item("A", 2), item("B", 3)]
    sess = sessions("X", 1, 90) + sessions("A", 1, 90) + sessions("B", 1, 20)
    plan = build(items, sess, cap_tolerance_minutes=0)
    assert table(plan)[1] == ["خواندن X1", "خواندن B1"]


def test_14_postpone():
    items, sess = base_input()
    sess = [dict(s, read_manual_date=d(3)) if s["id"] == "A1" else s for s in sess]
    plan = build(items, sess)
    assert day_of(plan, "A1", "read") == [3]
    assert day_of(plan, "B1", "read") == [1]


def test_15_manual_review_shifts_following_reviews():
    items = [item("A", 1)]
    sess = mark_read(sessions("A", 1, 60), "A1", d(0))   # مرور اول روز 1
    plan = build(items, sess)
    assert day_of(plan, "A1", "review") == [1, 4, 11, 41]
    moved = [dict(s, review_manual_date=d(3)) for s in sess]
    plan = build(items, moved)
    assert day_of(plan, "A1", "review") == [3, 6, 13, 43]  # همه 2 روز عقب‌تر


def test_16_inactive_item():
    items = [item("A", 1, is_active=False)]
    sess = mark_read(sessions("A", 2, 60), "A1", d(-20))
    sess = [dict(s, leitner_box=3, last_reviewed_on=d(-10)) if s["id"] == "A1" else s
            for s in sess]
    plan = build(items, sess)
    assert all_tasks(plan) == []

    items[0]["is_active"] = True
    plan = build(items, sess)
    review = plan["days"][0]["tasks"][0]
    assert review["session_id"] == "A1"
    assert review["review_round"] == 3   # جعبه سالم مانده
    assert review["overdue"]             # مرور عقب‌افتاده برگشته


def test_17_review_override_in_plan():
    items, sess = base_input()
    sess = [dict(s, review_minutes_override=5) if s["id"] == "A1" else s for s in sess]
    plan = build(items, sess)
    for day in plan["days"]:
        for t in day["tasks"]:
            if t["kind"] == "review":
                assert t["minutes"] == (5 if t["session_id"] == "A1" else 20)


def test_18_review_order_by_read_date():
    items = [item("Q", 1), item("Z", 2)]
    sess = sessions("Q", 1, 120) + sessions("Z", 1, 120)
    sess = mark_read(sess, "Z1", d(-5))   # Z در صف عقب‌تر است ولی زودتر خوانده شده
    sess = mark_read(sess, "Q1", d(-3))
    plan = build(items, sess, default_cap_minutes=40, cap_tolerance_minutes=0)
    assert table(plan)[1] == ["مرور Z1"]


def test_19_finish_dates():
    plan = build(*base_input())
    info = plan["items"]["A"]
    assert info["read_end"] == d(3)
    assert info["review_end"] == d(44)
    last_review = max(d(n) for n in day_of(plan, "A3", "review") + day_of(plan, "A1", "review"))
    assert info["review_end"] == last_review


def test_20_reset_item():
    items = [item("A", 1)]
    sess = [dict(s, status="finished", leitner_box=4) for s in sessions("A", 2, 60)]
    assert all_tasks(build(items, sess)) == []
    sess = [leitner.reset_session(s) for s in sess]
    plan = build(items, sess)
    assert day_of(plan, "A1", "read") == [1]
    assert day_of(plan, "A2", "read") == [2]


def test_21_deleted_item_frees_space():
    items, sess = base_input()
    items = [i for i in items if i["id"] != "A"]
    sess = [s for s in sess if s["item_id"] != "A"]
    plan = build(items, sess)
    assert table(plan)[1] == ["خواندن B1"]
    assert day_of(plan, "B2", "read") == [2]


def test_22_changed_intervals():
    items = [item("A", 1), item("K", 2, review_intervals=[1, 3, 7, 30])]
    sess = sessions("A", 1, 60) + sessions("K", 1, 60)
    sess = mark_read(sess, "A1", d(-10))
    sess = mark_read(sess, "K1", d(-10))
    plan = build(items, sess)
    assert day_of(plan, "A1", "review")[0] == 1   # عقب‌افتاده، امروز
    plan = build(items, sess, review_intervals=[20, 40])
    # خوانده‌شده در روز -10 + فاصلهٔ جدید 20 = روز 10، بعد 40 روز بعدش
    assert day_of(plan, "A1", "review") == [10, 50]
    assert day_of(plan, "K1", "review")[0] == 1   # فاصلهٔ اختصاصی، دست نخورده


def test_23_item_intervals_win():
    items = [item("A", 1, review_intervals=[2, 5]), item("B", 2)]
    plan = build(items, sessions("A", 1, 60) + sessions("B", 1, 60))
    assert day_of(plan, "A1", "review") == [3, 8]
    assert day_of(plan, "B1", "review") == [2, 5, 12, 42]


def test_24_weekday_caps_and_days_off():
    # DAY1 شنبه است (weekday=5). جمعه weekday=4.
    items = [item("A", 1, max_new_sessions_per_day=10)]
    sess = sessions("A", 20, 60)
    plan = build(items, sess, weekday_caps={5: 60}, weekly_days_off=[4])
    days = {day["date"]: day for day in plan["days"]}
    assert days[d(1)]["cap"] == 60 and days[d(1)]["total"] <= 60 + 30
    friday = d(7)
    assert friday.weekday() == 4
    assert days[friday]["tasks"] == []
    # تغییر همان روز بر هر دو مقدم است
    plan = build(items, sess, weekday_caps={5: 60}, weekly_days_off=[4],
                 overrides={d(1): 200, friday: 90})
    days = {day["date"]: day for day in plan["days"]}
    assert days[d(1)]["cap"] == 200
    assert days[friday]["cap"] == 90 and days[friday]["tasks"]


def test_25_review_cap():
    items = [item("R", 1), item("N", 2)]
    sess = sessions("R", 3, 120) + sessions("N", 1, 60)
    for sid in ("R1", "R2", "R3"):
        sess = mark_read(sess, sid, d(0))   # سه مرور 40 دقیقه‌ای امروز
    off = table(build(items, sess))
    assert off[1] == ["مرور R1", "مرور R2", "مرور R3"]   # خاموش: مرور اول
    on = table(build(items, sess, review_cap_percent=50))  # حداکثر 60 دقیقه مرور
    assert on[1] == ["مرور R1", "خواندن N1"]
    assert "مرور R2" in on[2]


def test_26_day_start_hour():
    assert scheduler.effective_today(datetime(2026, 1, 4, 1, 0), 4) == d(1)
    assert scheduler.effective_today(datetime(2026, 1, 4, 5, 0), 4) == d(2)


def test_partial_session_schedules_remaining_time_without_review():
    items = [item("A", 1)]
    sess = sessions("A", 1, 60, status="reading", minutes_done=45)
    plan = build(items, sess)
    first = plan["days"][0]["tasks"][0]
    assert (first["kind"], first["minutes"], first["partial"]) == ("read", 15, True)
    assert day_of(plan, "A1", "review")[0] == 2  # مرور فقط بعد از پایان خواندن


def test_horizon_warning():
    items = [item("A", 1)]
    plan = scheduler.build_plan(items, sessions("A", 3, 60), settings(), {}, DAY1,
                                horizon_days=1)
    assert plan["warnings"]


def test_speed_for_typical_data():
    # 50 درس × 20 جلسهٔ 45 دقیقه‌ای، بعضی در حال مرور
    items, sess = [], []
    for n in range(50):
        iid = f"I{n}-"
        items.append(item(iid, n, max_new_sessions_per_day=2))
        sess += sessions(iid, 20, 45)
    for s in sess[:200]:
        s.update(leitner.finish_reading(s, d(-5), [1, 3, 7, 30]))
    start = time.perf_counter()
    plan = build(items, sess)
    elapsed = time.perf_counter() - start
    print(f"\nزمان ساخت برنامه: {elapsed * 1000:.0f} میلی‌ثانیه، {len(plan['days'])} روز")
    assert not plan["warnings"]
    assert elapsed < 0.2
