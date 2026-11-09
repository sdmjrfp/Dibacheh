"""ترجمه‌ها: هیچ زبانی نباید متن جاافتاده یا جای خالی اشتباه داشته باشد."""

import re
import sys
from pathlib import Path

import pytest

import i18n
import jalali

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "static" / "i18n"
sys.path.insert(0, str(ROOT / "tools"))

import i18n_extract  # noqa: E402

KEYS = FOLDER.joinpath("keys.txt").read_text(encoding="utf-8").split("\n")
OTHER_LANGUAGES = [code for code in i18n.LANGUAGES if code != "fa"]


def test_every_text_in_the_code_has_a_key():
    missing = set(i18n_extract.all_texts()) - set(KEYS)
    assert not missing, "tools/i18n_extract.py را اجرا کنید"


def test_keys_are_unique():
    assert len(KEYS) == len(set(KEYS))


@pytest.mark.parametrize("code", OTHER_LANGUAGES)
def test_language_file_matches_keys(code):
    lines = FOLDER.joinpath(f"{code}.txt").read_text(encoding="utf-8").split("\n")
    assert len(lines) == len(KEYS)
    for key, line in zip(KEYS, lines, strict=True):
        assert bool(key) == bool(line), key
        assert sorted(re.findall(r"\{\d+\}", key)) == sorted(re.findall(r"\{\d+\}", line)), key


@pytest.mark.parametrize("code", OTHER_LANGUAGES)
def test_translations_are_not_left_in_persian(code):
    lines = FOLDER.joinpath(f"{code}.txt").read_text(encoding="utf-8").split("\n")
    if code == "ar":
        return   # عربی و فارسی خط مشترک دارند
    left = [line for line in lines if re.search(r"[؀-ۿ]", line)]
    assert not left, left[:5]


@pytest.fixture
def english():
    i18n.set_language("en")
    yield
    i18n.set_language("fa")


def test_persian_returns_the_key_with_values():
    assert i18n._("{0} باید عدد باشد.", "سرعت") == "سرعت باید عدد باشد."


def test_other_language_translates_and_fills_values(english):
    assert i18n._("{0} دقیقه", 5).startswith("5")
    assert "دقیقه" not in i18n._("{0} دقیقه", 5)
    assert i18n._("متنی که ترجمه ندارد") == "متنی که ترجمه ندارد"


def test_unknown_language_falls_back_to_persian():
    i18n.set_language("xx")
    assert i18n.current() == "fa"


def test_error_message_follows_language(client):
    client.patch("/api/settings", json={"language": "en"})
    response = client.post("/api/items", json={"title": " "})
    assert response.status_code == 400
    assert not re.search(r"[؀-ۿ]", response.get_json()["error"])
    client.patch("/api/settings", json={"language": "fa"})
    i18n.set_language("fa")


def test_page_has_language_direction_and_calendar(client):
    page = client.get("/").get_data(as_text=True)
    assert 'lang="fa" dir="rtl" data-calendar="persian" data-first-weekday="5"' in page
    client.patch("/api/settings", json={"language": "de", "calendar": "gregorian", "first_weekday": 0})
    page = client.get("/").get_data(as_text=True)
    assert 'lang="de" dir="ltr" data-calendar="gregorian" data-first-weekday="0"' in page
    client.patch("/api/settings", json={"language": "ar"})
    assert 'lang="ar" dir="rtl"' in client.get("/").get_data(as_text=True)
    i18n.set_language("fa")
    jalali.configure("persian", 5)


@pytest.mark.parametrize("bad", [{"language": "xx"}, {"calendar": "maya"}, {"first_weekday": 3}])
def test_invalid_language_settings_are_rejected(client, bad):
    assert client.patch("/api/settings", json=bad).status_code == 400


def test_gregorian_calendar_in_python():
    from datetime import date
    jalali.configure("gregorian", 0)
    try:
        assert jalali.iso_name(date(2026, 11, 5)) == "2026-11-05"
        assert jalali.month_bounds(date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))
        assert jalali.week_start(date(2026, 11, 5)) == date(2026, 11, 2)   # دوشنبه
        assert jalali.format_date(date(2026, 11, 5)) == "۵ نوامبر ۲۰۲۶"
    finally:
        jalali.configure("persian", 5)


def test_week_can_start_on_sunday():
    from datetime import date
    jalali.configure("gregorian", 6)
    try:
        assert jalali.week_start(date(2026, 11, 5)) == date(2026, 11, 1)
    finally:
        jalali.configure("persian", 5)


def test_export_in_english_is_left_to_right_with_gregorian_dates(client, tmp_path):
    client.patch("/api/settings", json={"language": "en", "calendar": "gregorian", "first_weekday": 0,
                                        "export_folder": str(tmp_path)})
    client.post("/api/items", json={"title": "Algebra", "session_count": 1, "session_minutes": 30})
    result = client.post("/api/export", json={"scope": "day", "with_content": False}).get_json()
    page = Path(result["path"]).read_text(encoding="utf-8")
    assert '<html lang="en" dir="ltr">' in page
    assert "Algebra" in page and "Noto Sans" in page
    assert not re.search(r"[؀-ۿ]", re.sub(r"<style>.*?</style>", "", page, flags=re.S).split("<script")[0])
    client.patch("/api/settings", json={"language": "fa", "calendar": "persian", "first_weekday": 5})
    i18n.set_language("fa")
    jalali.configure("persian", 5)
