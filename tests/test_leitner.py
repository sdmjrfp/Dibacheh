"""تست‌های قانون‌های لایتنر (سناریوهای 7، 8 و 17 بخش 13)."""

from fractions import Fraction

from helpers import d, item, sessions, settings

import leitner

INTERVALS = [1, 3, 7, 30]


def read_session():
    s = sessions("A", 1, 60)[0]
    return leitner.finish_reading(s, d(1), INTERVALS)


def test_finish_reading_goes_to_box_1():
    s = read_session()
    assert s["leitner_box"] == 1
    assert s["status"] == "reviewing"
    assert s["next_review_on"] == d(2)


def test_full_review_cycle_ends_finished():
    s = read_session()
    s = leitner.record_review(s, d(2), INTERVALS)
    assert (s["leitner_box"], s["next_review_on"]) == (2, d(5))
    s = leitner.record_review(s, d(5), INTERVALS)
    assert (s["leitner_box"], s["next_review_on"]) == (3, d(12))
    s = leitner.record_review(s, d(12), INTERVALS)
    assert (s["leitner_box"], s["next_review_on"]) == (4, d(42))
    s = leitner.record_review(s, d(42), INTERVALS)
    assert s["status"] == "finished"
    assert s["next_review_on"] is None


def test_scenario_7_needs_more_review():
    s = read_session()
    s = leitner.record_review(s, d(2), INTERVALS)
    s = leitner.record_review(s, d(5), INTERVALS)  # جعبهٔ 3
    s = leitner.needs_more_review(s, d(12), INTERVALS)
    assert s["leitner_box"] == 1
    assert s["next_review_on"] == d(13)


def test_scenario_8_late_review_keeps_box():
    s = read_session()
    s = leitner.record_review(s, d(2), INTERVALS)  # جعبهٔ 2، موعد روز 5
    s = leitner.record_review(s, d(9), INTERVALS)  # 4 روز دیر
    assert s["leitner_box"] == 3
    assert s["next_review_on"] == d(16)  # 9 + 7، از روز واقعی انجام


def test_review_minutes_is_one_third_rounded_up():
    s = sessions("A", 1, 50)[0]
    assert leitner.review_minutes(s, item("A", 1), settings()) == 17


def test_scenario_17_review_override():
    s = sessions("A", 1, 60, review_minutes_override=5)[0]
    assert leitner.review_minutes(s, item("A", 1), settings()) == 5


def test_item_ratio_beats_default():
    s = sessions("A", 1, 60)[0]
    assert leitner.review_minutes(s, item("A", 1, review_ratio="1/2"), settings()) == 30


def test_parse_ratio_forms():
    assert leitner.parse_ratio("1/3") == Fraction(1, 3)
    assert leitner.parse_ratio(0.5) == Fraction(1, 2)
    assert leitner.parse_ratio(None) == Fraction(1, 3)


def test_next_review_uses_new_intervals_and_clamps_box():
    s = read_session()
    s = leitner.record_review(s, d(2), INTERVALS)
    s = leitner.record_review(s, d(5), INTERVALS)
    s = leitner.record_review(s, d(12), INTERVALS)  # جعبهٔ 4
    # فاصله‌ها به دو فاصله کم شد: جعبهٔ 4 به آخرین جعبه (2) می‌رود
    assert leitner.next_review_date(s, [2, 10]) == d(22)


def test_reset_session():
    s = leitner.reset_session(read_session())
    assert s["status"] == "unread"
    assert s["leitner_box"] == 0
    assert s["read_at"] is None
    assert s["minutes"] == 60
