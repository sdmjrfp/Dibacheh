"""ساخت خروجی HTML روزانه، هفتگی و ماهانه.

خروجی یک فایل HTML مستقل است: فونت، CSS و عکس‌ها همه داخل همان فایل‌اند،
پس روی گوشی بدون اینترنت و بدون فایل دیگری باز می‌شود.

محتوای هر کار:
  نوت Markdown   متن همان بخش، تبدیل‌شده به HTML (لینک‌های Obsidian به متن ساده)
  PDF            عکس همان صفحه‌ها
  لینک           فقط آدرس
  ویدیوی محلی    فقط نام و آدرس (به خاطر حجم)
"""

import base64
import html
import io
import re
from datetime import timedelta
from pathlib import Path

import markdown

import jalali
import sources

PROJECT_DIR = Path(__file__).resolve().parent
FONT_FILE = PROJECT_DIR / "static" / "vendor" / "vazirmatn" / "Vazirmatn-Variable.woff2"

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
VIDEO_TYPES = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}

# کیفیت عکس صفحه‌های PDF: scale=1.6 حدود 115 نقطه در اینچ است؛ برای خواندن روی گوشی کافی است.
PDF_SCALE = 1.6
PDF_JPEG_QUALITY = 72
PDF_MAX_PAGES = 60   # جلوی ساختن فایل‌های خیلی بزرگ را می‌گیرد

KIND_LABEL = {"read": "خواندن", "review": "مرور", "routine": "روتین"}

esc = html.escape


# ---------------------------------------------------------------------------
# بازهٔ خروجی و نام فایل
# ---------------------------------------------------------------------------

def export_range(scope, day):
    """اولین و آخرین روز خروجی و نام فایل. scope: day، week یا month."""
    if scope == "day":
        return day, day, f"برنامهٔ روز {jalali.iso_name(day)}.html"
    if scope == "week":
        start = jalali.week_start(day)
        return start, start + timedelta(days=6), f"برنامهٔ هفته از {jalali.iso_name(start)}.html"
    if scope == "month":
        first, last = jalali.month_bounds(day)
        return first, last, f"برنامهٔ ماه {jalali.iso_name(first)[:7]}.html"
    raise ValueError("scope نامعتبر")


def export(state, scope, day, with_content, vault_path, folder):
    """فایل خروجی را می‌سازد و در folder ذخیره می‌کند. خروجی: آدرس فایل.

    state: همان داده‌هایی که صفحه دارد (درس‌ها با جلسه‌ها، برنامه، سابقه، امروز).
    """
    start, end, name = export_range(scope, day)
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(render(state, scope, start, end, with_content, vault_path), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# ساخت HTML
# ---------------------------------------------------------------------------

def render(state, scope, start, end, with_content, vault_path):
    items = {item["id"]: item for item in state["items"]}
    sessions = {s["id"]: (items[s["item_id"]], s) for item in state["items"] for s in item["sessions"]}
    plan_days = {d["date"]: d for d in state["plan"]["days"]}
    done = {}
    for entry in state.get("history", []):
        done.setdefault(entry["date"], []).append(entry)
    today = state["today"]

    titles = {"day": "برنامهٔ روز", "week": "برنامهٔ هفته", "month": "برنامهٔ ماه"}
    if scope == "day":
        heading = f"{titles[scope]}: {jalali.format_date(start, weekday=True)}"
    elif scope == "week":
        heading = f"{titles[scope]}: {jalali.format_date(start)} تا {jalali.format_date(end)}"
    else:
        y, m, _ = jalali.to_jalali(start)
        heading = f"{titles[scope]}: {jalali.MONTHS[m - 1]} {jalali.fa(y)}"

    body = []
    day = start
    while day <= end:
        body.append(day_html(day, plan_days.get(day), done.get(day, []), sessions, today,
                             with_content, vault_path, show_title=scope != "day"))
        day += timedelta(days=1)

    note = f"ساخته‌شده در {jalali.format_date(today)}."
    if end > today:
        note += " برنامهٔ روزهای آینده پیش‌بینی است و با هر تغییر روی Mac عوض می‌شود."
    note += " تیک‌های این صفحه فقط برای خودتان است و به Mac برنمی‌گردد."
    return PAGE.format(title=esc(heading), heading=esc(heading), note=esc(note),
                       font=_font_data(), body="\n".join(body))


def day_html(day, plan_day, done_entries, sessions, today, with_content, vault_path, show_title):
    parts = []
    if show_title:
        parts.append(f'<h2>{esc(jalali.format_date(day, weekday=True))}</h2>')
    if plan_day and plan_day["is_off"]:
        parts.append('<p class="muted">تعطیل</p>')
    for entry in done_entries:
        info = sessions.get(entry["session_id"])
        title = info[0]["title"] if info else "درس حذف‌شده"
        parts.append(
            f'<div class="task done kind-{esc(entry["task_type"])}">✓ {esc(title)} · '
            f'{esc(KIND_LABEL.get(entry["task_type"], ""))} · {jalali.fa(entry["minutes"])} دقیقه</div>')
    tasks = plan_day["tasks"] if plan_day and day >= today else []
    for n, task in enumerate(tasks):
        info = sessions.get(task["session_id"])
        if info:
            parts.append(task_html(task, info[0], info[1], with_content, vault_path, f"{day}-{n}"))
    if not tasks and not done_entries and not (plan_day and plan_day["is_off"]):
        parts.append('<p class="muted">کاری نیست.</p>')
    if plan_day and tasks:
        total = sum(t["minutes"] for t in tasks)
        parts.insert(1 if show_title else 0,
                     f'<p class="muted">جمع: {jalali.fa(total)} دقیقه</p>')
    return f'<section class="day">{"".join(parts)}</section>'


def task_html(task, item, session, with_content, vault_path, key):
    label = KIND_LABEL[task["kind"]]
    if task["kind"] == "review":
        label += f" {jalali.fa(task['review_round'])}"
    section = sources.section_text(item, session)
    meta = [label, f"جلسهٔ {jalali.fa(session['sequence'])}"]
    if section:
        meta.append(section)
    meta.append(f"{jalali.fa(task['minutes'])} دقیقه")
    head = (f'<label class="task-head"><input type="checkbox" id="t{esc(key)}"> '
            f'<strong>{esc(item["title"])}</strong>'
            f'<span class="meta">{esc(" · ".join(meta))}</span></label>')
    content = ""
    if with_content and task["kind"] != "routine":
        content = content_html(item, session, vault_path)
    return f'<div class="task kind-{task["kind"]}">{head}{content}</div>'


# ---------------------------------------------------------------------------
# محتوای منبع
# ---------------------------------------------------------------------------

def content_html(item, session, vault_path):
    """محتوای همان بخش منبع برای خواندن روی گوشی."""
    kind = item["source_type"]
    if kind == "none":
        return ""
    if kind == "url":
        url = item.get("source_path_or_url") or ""
        return f'<div class="content"><p>لینک: <span dir="ltr" class="url">{esc(url)}</span></p></div>'
    location = sources.source_location(item, vault_path)
    if location is None or not location.exists():
        return '<div class="content"><p class="muted">منبع پیدا نشد (شاید جابه‌جا شده است).</p></div>'
    suffix = location.suffix.lower()
    try:
        if suffix == ".md":
            return f'<div class="content md">{markdown_html(location, item, session, vault_path)}</div>'
        if suffix == ".pdf":
            return f'<div class="content">{pdf_html(location, item, session)}</div>'
        if suffix in IMAGE_TYPES:
            return f'<div class="content"><img src="{_data_uri(location)}" alt=""></div>'
    except Exception as error:  # یک منبع خراب نباید کل خروجی را خراب کند
        return f'<div class="content"><p class="muted">خواندن منبع ممکن نشد: {esc(str(error))}</p></div>'
    what = "ویدیو" if suffix in VIDEO_TYPES else "فایل"
    return (f'<div class="content"><p>{what}: {esc(location.name)}<br>'
            f'<span dir="ltr" class="url">{esc(str(location))}</span></p></div>')


def pdf_html(path, item, session):
    """صفحه‌های همان جلسه از PDF، به شکل عکس."""
    import pypdfium2 as pdfium  # فقط وقتی لازم است بار می‌شود

    if item.get("section_unit") != "page" or not session.get("section_start"):
        return '<p class="muted">بازهٔ صفحهٔ این جلسه مشخص نشده است.</p>'
    first = int(session["section_start"])
    last = int(session.get("section_end") or first)
    doc = pdfium.PdfDocument(str(path))
    try:
        count = len(doc)
        first, last = max(1, first), min(last, count, first + PDF_MAX_PAGES - 1)
        parts = []
        for number in range(first, last + 1):
            image = doc[number - 1].render(scale=PDF_SCALE).to_pil().convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=PDF_JPEG_QUALITY, optimize=True)
            data = base64.b64encode(buffer.getvalue()).decode()
            parts.append(f'<figure><img src="data:image/jpeg;base64,{data}" alt="صفحهٔ {number}">'
                         f'<figcaption>صفحهٔ {jalali.fa(number)}</figcaption></figure>')
    finally:
        doc.close()
    return "".join(parts)


def markdown_html(path, item, session, vault_path):
    text = path.read_text(encoding="utf-8", errors="replace")
    text = _strip_frontmatter(text)
    if item.get("section_unit") == "heading" and session.get("section_start"):
        text = markdown_section(text, session["section_start"], session.get("section_end"))
    text = _obsidian_to_markdown(text, path.parent, vault_path)
    result = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])
    # اسکریپت داخل نوت در خروجی اجرا نمی‌شود
    return re.sub(r"<script\b.*?</script>", "", result, flags=re.S | re.I)


def markdown_section(text, start_heading, end_heading=None):
    """بخشی از نوت: از عنوان start تا آخر بخشِ عنوان end (یا تا آخر بخش start).

    آخر بخش = عنوان بعدی‌ای که هم‌سطح یا بالاتر از آن عنوان باشد.
    """
    lines = text.splitlines()
    headings = []  # (شمارهٔ خط، سطح، متن)
    in_code = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match and not in_code:
            headings.append((i, len(match.group(1)), match.group(2)))

    def find(name, after=-1):
        return next((h for h in headings if h[2] == name and h[0] > after), None)

    start = find(start_heading)
    if start is None:
        return text  # عنوان پیدا نشد: کل نوت
    last = find(end_heading, start[0] - 1) if end_heading else start
    last = last or start
    end_line = len(lines)
    for line_no, level, _ in headings:
        if line_no > last[0] and level <= last[1]:
            end_line = line_no
            break
    return "\n".join(lines[start[0]:end_line])


def _strip_frontmatter(text):
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def _obsidian_to_markdown(text, note_dir, vault_path):
    """نوشته‌های مخصوص Obsidian را به Markdown معمولی تبدیل می‌کند."""

    def embed(match):
        target = match.group(1).split("|")[0].strip()
        image = _find_file(target, note_dir, vault_path)
        if image is not None and image.suffix.lower() in IMAGE_TYPES:
            return f'<img src="{_data_uri(image)}" alt="">'
        return f"*({target})*"

    text = re.sub(r"!\[\[([^\]]+)\]\]", embed, text)                         # ![[عکس.png]]
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)                # [[نوت|متن]]
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda m: m.group(1).split("#")[0], text)  # [[نوت]]
    text = re.sub(r"==([^=\n]+)==", r"<mark>\1</mark>", text)                 # ==هایلایت==

    def local_image(match):
        alt, target = match.group(1), match.group(2)
        if re.match(r"^[a-z]+:", target):
            return match.group(0)  # عکس اینترنتی: همان‌طور می‌ماند (آفلاین نمایش داده نمی‌شود)
        image = _find_file(target, note_dir, vault_path)
        if image is not None and image.suffix.lower() in IMAGE_TYPES:
            return f'<img src="{_data_uri(image)}" alt="{esc(alt)}">'
        return match.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", local_image, text)


def _find_file(name, note_dir, vault_path):
    """فایل جاسازی‌شده را کنار نوت، یا جایی داخل والت پیدا می‌کند."""
    candidate = (note_dir / name)
    if candidate.is_file():
        return candidate
    if vault_path:
        vault = Path(vault_path).expanduser()
        direct = vault / name
        if direct.is_file():
            return direct
        for found in vault.rglob(Path(name).name):
            if found.is_file():
                return found
    return None


def _data_uri(path):
    mime = IMAGE_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"


def _font_data():
    if FONT_FILE.exists():
        return base64.b64encode(FONT_FILE.read_bytes()).decode()
    return ""


# ---------------------------------------------------------------------------
# قالب صفحه. همهٔ CSS داخل خود فایل است.
# ---------------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
@font-face {{ font-family: "Vazirmatn"; src: url(data:font/woff2;base64,{font}) format("woff2"); font-weight: 100 900; }}
:root {{ --bg: #f6f6f3; --panel: #fff; --text: #1f2328; --muted: #6b7280; --border: #e3e3de;
        --read: #2f6f5e; --review: #3b5ba9; --routine: #8a5a14; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #16181b; --panel: #1e2125; --text: #e6e6e3; --muted: #9aa0a8; --border: #31353b;
          --read: #6fbfa5; --review: #8ea8ec; --routine: #d6a65c; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 16px; background: var(--bg); color: var(--text);
       font-family: "Vazirmatn", system-ui, Tahoma, sans-serif; line-height: 1.8; font-size: 17px; }}
main {{ max-width: 860px; margin: 0 auto; }}
h1 {{ font-size: 1.3em; margin: 0 0 4px; }}
h2 {{ font-size: 1.1em; margin: 0 0 6px; }}
.muted {{ color: var(--muted); font-size: 0.9em; }}
.day {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin: 12px 0; }}
.task {{ border: 1px solid var(--border); border-inline-start: 5px solid var(--read); border-radius: 8px;
        padding: 8px 10px; margin: 8px 0; }}
.task.kind-review {{ border-inline-start-color: var(--review); }}
.task.kind-routine {{ border-inline-start-color: var(--routine); }}
.task.done {{ color: var(--muted); border-style: dashed; }}
.task-head {{ display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; cursor: pointer; }}
.task-head input {{ width: 1.3em; height: 1.3em; }}
.task-head input:checked ~ strong {{ text-decoration: line-through; color: var(--muted); }}
.meta {{ color: var(--muted); font-size: 0.85em; }}
.content {{ margin-top: 8px; border-top: 1px solid var(--border); padding-top: 8px; overflow-wrap: anywhere; }}
.content p, .content li, .content td, .content th {{ unicode-bidi: plaintext; }}
.content img {{ max-width: 100%; height: auto; }}
.content pre {{ direction: ltr; text-align: left; overflow-x: auto; background: var(--bg); padding: 8px; border-radius: 6px; }}
.content table {{ border-collapse: collapse; }}
.content td, .content th {{ border: 1px solid var(--border); padding: 4px 8px; }}
figure {{ margin: 8px 0; }}
figure img {{ border: 1px solid var(--border); }}
figcaption {{ color: var(--muted); font-size: 0.8em; text-align: center; }}
.url {{ word-break: break-all; }}
</style>
</head>
<body>
<main>
<h1>{heading}</h1>
<p class="muted">{note}</p>
{body}
</main>
</body>
</html>
"""
