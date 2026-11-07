"""تست‌های منابع: تشخیص والت، لینک شکسته، دستور باز کردن و تقسیم بازه."""

import sources


def study(**extra):
    data = {"source_type": "none", "source_path_or_url": None, "section_unit": "text",
            "range_start": None, "range_end": None}
    data.update(extra)
    return data


def test_path_inside_vault_is_stored_relative(tmp_path):
    vault = tmp_path / "Vault"
    (vault / "زبان").mkdir(parents=True)
    note = vault / "زبان" / "درس 1.md"
    note.write_text("# سلام")
    assert sources.classify_path(note, vault) == ("vault", "زبان/درس 1.md")


def test_path_outside_vault_is_stored_full(tmp_path):
    other = tmp_path / "Books" / "book.pdf"
    other.parent.mkdir()
    other.write_text("x")
    assert sources.classify_path(other, tmp_path / "Vault") == ("file", str(other.resolve()))


def test_broken_link_is_reported(tmp_path):
    note = tmp_path / "a.pdf"
    note.write_text("x")
    item = study(source_type="file", source_path_or_url=str(note))
    assert sources.check_source(item, "") is None
    note.rename(tmp_path / "b.pdf")                       # کاربر نام فایل را عوض کرد
    assert "پیدا نشد" in sources.check_source(item, "")


def test_open_command_for_each_source_type(tmp_path):
    vault = tmp_path / "My Vault"
    cmd = sources.open_command(study(source_type="vault", source_path_or_url="زبان/درس 1.md"), str(vault))
    assert cmd[-1].startswith("obsidian://open?vault=My%20Vault&file=")
    assert "%2F" in cmd[-1]                                # «/» داخل آدرس رمزگذاری شده
    pdf = tmp_path / "a.pdf"
    assert sources.open_command(study(source_type="file", source_path_or_url=str(pdf)), "")[-1] == str(pdf)
    assert sources.open_command(study(source_type="url", source_path_or_url="https://youtu.be/x"), "")[-1] == "https://youtu.be/x"


def test_only_web_links_are_opened():
    assert sources.open_command(study(source_type="url", source_path_or_url="file:///etc/passwd"), "") is None
    assert sources.open_command(study(source_type="url", source_path_or_url="javascript:alert(1)"), "") is None
    assert sources.open_command(study(), "") is None


def test_markdown_headings(tmp_path):
    note = tmp_path / "n.md"
    note.write_text("# فصل ۱\nمتن\n## بخش الف\n```\n# این کد است\n```\n# فصل ۲ #\n", encoding="utf-8")
    item = study(source_type="file", source_path_or_url=str(note))
    assert sources.markdown_headings(item, "") == [
        {"level": 1, "text": "فصل ۱"}, {"level": 2, "text": "بخش الف"}, {"level": 1, "text": "فصل ۲"}]


def test_split_pages():
    assert sources.split_range("page", "1", "150", 10)[0] == ("1", "15")
    assert sources.split_range("page", "1", "150", 10)[-1] == ("136", "150")
    assert sources.split_range("page", "1", "10", 3) == [("1", "4"), ("5", "7"), ("8", "10")]
    assert sources.split_range("page", "1", "2", 3) is None          # صفحه کمتر از جلسه
    assert sources.split_range("text", "", "", 3) is None


def test_split_time():
    assert sources.split_range("time", "0:00", "1:30:00", 3) == [
        ("0:00", "30:00"), ("30:00", "1:00:00"), ("1:00:00", "1:30:00")]


def test_check_ranges():
    item = study(section_unit="page", range_start="1", range_end="30")
    good = [{"sequence": 1, "section_start": "1", "section_end": "15"},
            {"sequence": 2, "section_start": "16", "section_end": "30"}]
    assert sources.check_ranges(item, good) == []
    gap = [{"sequence": 1, "section_start": "1", "section_end": "10"},
           {"sequence": 2, "section_start": "16", "section_end": "30"}]
    assert any("فاصله" in p for p in sources.check_ranges(item, gap))
    short = [{"sequence": 1, "section_start": "1", "section_end": "20"}]
    assert any("پایان بازه" in p for p in sources.check_ranges(item, short))


def test_section_text():
    item = study(section_unit="page")
    assert sources.section_text(item, {"section_start": "1", "section_end": "15"}) == "صفحهٔ 1 تا 15"
    assert sources.section_text(study(), {"section_label": "فصل ۱"}) == "فصل ۱"
