"""تست‌های خروجی HTML."""

import io
import re

import pypdfium2 as pdfium
import pytest
from test_api import add, item_named
from test_calendar_api import today_of

import exporter
import platform_tools


def make_pdf(path, pages):
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(300, 400)
    buffer = io.BytesIO()
    doc.save(buffer)
    path.write_bytes(buffer.getvalue())


@pytest.fixture
def export_dir(client, tmp_path):
    folder = tmp_path / "exports"
    client.patch("/api/settings", json={"export_folder": str(folder)})
    return folder


def export(client, **body):
    response = client.post("/api/export", json=body)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

NOTE = """---
tags: [x]
---
# فصل ۱
متن فصل یک با [[نوت دیگر|لینک]] و [[نوت سوم]] و ==مهم==.
## بخش الف
الف
# فصل ۲
دو
## بخش ب
ب
# فصل ۳
سه
"""


def test_markdown_section_single_heading():
    part = exporter.markdown_section(NOTE, "فصل ۲")
    assert "دو" in part and "بخش ب" in part
    assert "سه" not in part and "الف" not in part


def test_markdown_section_range():
    part = exporter.markdown_section(NOTE, "بخش الف", "فصل ۲")
    assert "الف" in part and "دو" in part and "ب" in part
    assert "سه" not in part and "متن فصل یک" not in part


def test_obsidian_syntax_becomes_plain(tmp_path):
    note = tmp_path / "n.md"
    note.write_text(NOTE, encoding="utf-8")
    (tmp_path / "pic.png").write_bytes(b"\x89PNG fake")
    note.write_text(NOTE + "\n![[pic.png]]\n<script>alert(1)</script>\n", encoding="utf-8")
    item = {"source_type": "file", "source_path_or_url": str(note), "section_unit": "text"}
    out = exporter.markdown_html(note, item, {"section_start": None}, "")
    assert "لینک" in out and "[[" not in out and "نوت سوم" in out
    assert "<mark>مهم</mark>" in out
    assert "data:image/png;base64," in out
    assert "<script" not in out
    assert "tags:" not in out   # frontmatter حذف شد


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def test_pdf_pages_become_images(tmp_path):
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf, 5)
    item = {"section_unit": "page"}
    out = exporter.pdf_html(pdf, item, {"section_start": "2", "section_end": "4"})
    assert out.count("<img") == 3
    assert "صفحهٔ ۲" in out and "صفحهٔ ۴" in out and "صفحهٔ ۵" not in out


# ---------------------------------------------------------------------------
# خروجی کامل از راه API
# ---------------------------------------------------------------------------

def test_daily_export_with_pdf_and_note(client, export_dir, tmp_path):
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf, 30)
    note = tmp_path / "note.md"
    note.write_text(NOTE, encoding="utf-8")
    add(client, "کتاب", count=2, section_unit="page", range_start="1", range_end="30",
        source_type="file", source_path_or_url=str(pdf))
    state = add(client, "گرامر", count=1, minutes=30, section_unit="heading",
                source_type="file", source_path_or_url=str(note))
    s = item_named(state, "گرامر")["sessions"][0]
    client.patch(f"/api/sessions/{s['id']}", json={"section_start": "فصل ۲", "section_end": "فصل ۲"})

    result = export(client, scope="day", date=today_of(state).isoformat())
    path = export_dir / result["name"]
    html = path.read_text(encoding="utf-8")
    assert result["name"].startswith("برنامهٔ روز ")
    assert html.count('<img src="data:image/jpeg') == 15           # صفحهٔ 1 تا 15
    assert "<p>دو</p>" in html and "<p>سه</p>" not in html     # فقط بخش «فصل ۲»
    assert 'type="checkbox"' in html
    assert "data:font/woff2;base64," in html                         # فونت داخل فایل


def test_export_has_no_internet_links(client, export_dir):
    add(client, "ویدیو", count=1, source_type="url", source_path_or_url="https://youtu.be/abc")
    html = (export_dir / export(client, scope="day")["name"]).read_text(encoding="utf-8")
    assert "https://youtu.be/abc" in html                            # آدرس به شکل متن هست
    assert not re.search(r'(src|href)\s*=\s*"https?:', html)         # ولی هیچ چیزی از اینترنت بار نمی‌شود


def test_weekly_export_is_list_only_by_default(client, export_dir, tmp_path):
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf, 10)
    add(client, "کتاب", count=5, section_unit="page", range_start="1", range_end="10",
                source_type="file", source_path_or_url=str(pdf))
    html = (export_dir / export(client, scope="week")["name"]).read_text(encoding="utf-8")
    assert "<img" not in html
    assert html.count('class="day"') == 7
    html = (export_dir / export(client, scope="week", with_content=True)["name"]).read_text(encoding="utf-8")
    assert "<img" in html


def test_monthly_export_covers_whole_jalali_month(client, export_dir):
    state = add(client, "A", count=1)
    result = export(client, scope="month")
    html = (export_dir / result["name"]).read_text(encoding="utf-8")
    import jalali
    first, last = jalali.month_bounds(today_of(state))
    assert html.count('class="day"') == (last - first).days + 1


def test_done_tasks_appear_in_todays_export(client, export_dir):
    state = add(client, "A", count=2)
    s1 = item_named(state, "A")["sessions"][0]["id"]
    client.post("/api/tasks/done", json={"session_id": s1, "kind": "read", "result": "done"})
    html = (export_dir / export(client, scope="day")["name"]).read_text(encoding="utf-8")
    assert "✓ A" in html


def test_export_file_endpoint_only_serves_export_files(client, export_dir):
    add(client, "A", count=1)
    name = export(client, scope="day")["name"]
    assert client.get(f"/api/export/file/{name}").status_code == 200
    assert client.get("/api/export/file/../../etc/passwd").status_code in (400, 404)
    assert client.get("/api/export/file/x.txt").status_code == 400


def test_reveal_in_finder(client, export_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(platform_tools.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    add(client, "A", count=1)
    name = export(client, scope="day")["name"]
    client.post("/api/export/reveal", json={"name": name})
    assert calls == [platform_tools.reveal_args(export_dir / name)]
    assert client.post("/api/export/reveal", json={"name": "../x.html"}).status_code == 400
