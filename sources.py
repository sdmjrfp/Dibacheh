"""منابع درسی: Browse، ذخیرهٔ آدرس، باز کردن منبع و بخش هر جلسه.

قانون امنیتی مهم: برنامه فقط منبعی را باز یا می‌خواند که برای یک درس ثبت شده است.
هیچ تابعی در این فایل آدرس دلخواه را از مرورگر نمی‌گیرد تا باز کند.

برای اجرای open و osascript از subprocess با فهرست آرگومان (بدون shell=True)
استفاده می‌شود، تا نام فایل‌های عجیب نتوانند دستور اضافه اجرا کنند.
"""

import re
import subprocess
from pathlib import Path
from urllib.parse import quote, urlparse

# ---------------------------------------------------------------------------
# Browse با پنجرهٔ انتخاب فایل خود macOS
# ---------------------------------------------------------------------------

def browse(kind="file", prompt="یک فایل انتخاب کنید"):
    """پنجرهٔ انتخاب فایل یا پوشهٔ macOS را باز می‌کند و آدرس کامل را برمی‌گرداند.

    مرورگر به دلایل امنیتی آدرس کامل فایل را نمی‌دهد، برای همین این کار
    در بخش پایتون و با osascript انجام می‌شود.
    خروجی None یعنی کاربر Cancel زد.
    """
    what = "folder" if kind == "folder" else "file"
    # متن prompt داخل AppleScript قرار می‌گیرد، پس علامت " از آن حذف می‌شود
    safe_prompt = prompt.replace('"', "").replace("\\", "")
    script = f'POSIX path of (choose {what} with prompt "{safe_prompt}")'
    # activate باعث می‌شود پنجره جلوی مرورگر باز شود
    result = subprocess.run(
        ["osascript", "-e", "activate", "-e", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    if kind == "folder":
        path = path.rstrip("/")
    return path or None


def classify_path(path, vault_path):
    """تصمیم می‌گیرد آدرس انتخاب‌شده داخل والت Obsidian است یا بیرون آن.

    خروجی: (source_type، آدرس ذخیره‌شدنی)
      داخل والت → ("vault"، آدرس نسبت به والت)
      بیرون والت → ("file"، آدرس کامل)
    """
    full = Path(path).expanduser().resolve()
    if vault_path:
        vault = Path(vault_path).expanduser().resolve()
        if full.is_relative_to(vault):
            return "vault", full.relative_to(vault).as_posix()
    return "file", str(full)


def source_location(item, vault_path):
    """آدرس کامل فایل یک درس روی Mac، یا None برای لینک و کار بدون منبع."""
    stored = item.get("source_path_or_url")
    if not stored:
        return None
    if item["source_type"] == "vault":
        if not vault_path:
            return None
        return Path(vault_path).expanduser() / stored
    if item["source_type"] == "file":
        return Path(stored).expanduser()
    return None


def check_source(item, vault_path):
    """آیا منبع درس سر جایش هست؟ خروجی: None یعنی سالم، وگرنه متن خطا."""
    kind = item["source_type"]
    if kind == "none":
        return None
    if kind == "url":
        return None if is_web_url(item.get("source_path_or_url")) else "لینک معتبر نیست."
    if kind == "vault" and not vault_path:
        return "مسیر والت Obsidian در تنظیمات ثبت نشده است."
    location = source_location(item, vault_path)
    if location is None or not location.exists():
        return "فایل پیدا نشد. شاید تغییر نام داده یا جابه‌جا شده است. دوباره Browse کنید."
    return None


def open_command(item, vault_path):
    """دستوری که منبع درس را باز می‌کند، به شکل فهرست آرگومان.

    جدا از open_source است تا بدون باز شدن واقعی برنامه‌ها تست شود.
    """
    kind = item["source_type"]
    stored = item.get("source_path_or_url")
    if kind == "vault":
        vault_name = Path(vault_path).expanduser().name
        url = f"obsidian://open?vault={quote(vault_name, safe='')}&file={quote(stored, safe='')}"
        return ["open", url]
    if kind == "file":
        return ["open", str(Path(stored).expanduser())]
    if kind == "url" and is_web_url(stored):
        return ["open", stored]
    return None


def open_source(item, vault_path):
    """منبع یک درس ثبت‌شده را باز می‌کند. خروجی: None یعنی موفق، وگرنه متن خطا."""
    problem = check_source(item, vault_path)
    if problem:
        return problem
    command = open_command(item, vault_path)
    if command is None:
        return "این کار منبعی برای باز کردن ندارد."
    subprocess.run(command, check=False)
    return None


def is_web_url(value):
    """فقط لینک‌های http و https باز می‌شوند، نه file:// یا دستورهای دیگر."""
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


# ---------------------------------------------------------------------------
# عنوان‌های Markdown
# ---------------------------------------------------------------------------

def markdown_headings(item, vault_path):
    """فهرست عنوان‌های فایل Markdown ثبت‌شدهٔ یک درس، برای انتخاب بخش جلسه."""
    location = source_location(item, vault_path)
    if location is None or location.suffix.lower() != ".md" or not location.exists():
        return []
    headings = []
    in_code = False
    for line in location.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code  # «#» داخل بلوک کد عنوان نیست
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match and not in_code:
            headings.append({"level": len(match.group(1)), "text": match.group(2)})
    return headings


# ---------------------------------------------------------------------------
# بخش هر جلسه: تقسیم خودکار و بررسی
# ---------------------------------------------------------------------------

def parse_time(text):
    """"1:05:30" یا "65:30" یا "90" (دقیقه) را به ثانیه تبدیل می‌کند."""
    parts = [int(p) for p in str(text).strip().split(":")]
    if len(parts) == 1:
        return parts[0] * 60
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def format_time(seconds):
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def split_range(unit, start, end, count):
    """کل بازهٔ درس را به‌طور مساوی بین count جلسه تقسیم می‌کند.

    خروجی: فهرست (شروع، پایان) به شکل متن، یا None اگر این نوع بخش تقسیم‌شدنی نیست.
    صفحه‌ها پشت‌سرهم و بدون فاصله‌اند: 1-15، 16-30، ...
    زمان‌ها هم پشت‌سرهم: 0:00-15:00، 15:00-30:00، ...
    """
    if count <= 0 or start in (None, "") or end in (None, ""):
        return None
    if unit == "page":
        first, last = int(start), int(end)
        total = last - first + 1
        if total < count:
            return None
        base, extra = divmod(total, count)
        result, page = [], first
        for i in range(count):
            size = base + (1 if i < extra else 0)
            result.append((str(page), str(page + size - 1)))
            page += size
        return result
    if unit == "time":
        first, last = parse_time(start), parse_time(end)
        if last <= first:
            return None
        step = (last - first) / count
        points = [round(first + step * i) for i in range(count)] + [last]
        return [(format_time(points[i]), format_time(points[i + 1])) for i in range(count)]
    return None


def check_ranges(item, sessions):
    """بازه‌های جلسه‌ها با هم و با کل بازهٔ درس می‌خوانند؟

    خروجی: فهرست متن مشکل‌ها. فهرست خالی یعنی همه‌چیز درست است.
    فقط برای صفحه و زمان بررسی می‌شود.
    """
    unit = item.get("section_unit")
    if unit not in ("page", "time") or not sessions:
        return []
    convert = int if unit == "page" else parse_time
    gap = 1 if unit == "page" else 0  # صفحهٔ بعدی از +1 شروع می‌شود، زمان از همان لحظه
    problems = []
    ordered = sorted(sessions, key=lambda s: s["sequence"])
    try:
        ranges = [(s["sequence"], convert(s["section_start"]), convert(s["section_end"])) for s in ordered]
    except (TypeError, ValueError):
        return ["بازهٔ بعضی جلسه‌ها خالی یا نامعتبر است."]
    for seq, a, b in ranges:
        if b < a:
            problems.append(f"جلسهٔ {seq}: پایان قبل از شروع است.")
    for (seq1, _, end1), (seq2, start2, _) in zip(ranges, ranges[1:]):
        if start2 > end1 + gap:
            problems.append(f"بین جلسهٔ {seq1} و {seq2} فاصله افتاده است.")
        elif start2 < end1 + gap:
            problems.append(f"جلسهٔ {seq1} و {seq2} روی هم افتاده‌اند.")
    if item.get("range_start") not in (None, "") and item.get("range_end") not in (None, ""):
        if ranges[0][1] != convert(item["range_start"]):
            problems.append("جلسهٔ اول از شروع بازهٔ درس شروع نمی‌شود.")
        if ranges[-1][2] != convert(item["range_end"]):
            problems.append("جلسهٔ آخر به پایان بازهٔ درس نمی‌رسد.")
    return problems


def section_text(item, session):
    """متن بخش جلسه برای نمایش، مثل «صفحهٔ 1 تا 15»."""
    unit = item.get("section_unit")
    a, b = session.get("section_start"), session.get("section_end")
    if unit == "page" and a:
        return f"صفحهٔ {a} تا {b}" if b and b != a else f"صفحهٔ {a}"
    if unit == "time" and a:
        return f"از {a} تا {b}"
    if unit == "heading" and a:
        return f"از «{a}» تا «{b}»" if b and b != a else f"«{a}»"
    return session.get("section_label") or ""


# ---------------------------------------------------------------------------
# فونت‌ها
# ---------------------------------------------------------------------------

def font_family_name(path):
    """نام خانوادهٔ یک فایل فونت، مثلاً «Shabnam»."""
    from PIL import ImageFont
    return ImageFont.truetype(str(path), 12).getname()[0]


# فونت‌های فارسی رایگان و متن‌باز که همراه برنامه‌اند (static/vendor/fonts).
# مجوز هر فونت کنار فایل‌هایش است. فونت‌هایی که bold ندارند، ضخیمی را مرورگر می‌سازد.
BUNDLED_FONTS = [
    {"family": "Samim", "label": "صمیم", "regular": "samim/Samim.woff2", "bold": "samim/Samim-Bold.woff2"},
    {"family": "Shabnam", "label": "شبنم", "regular": "shabnam/Shabnam.woff2", "bold": "shabnam/Shabnam-Bold.woff2"},
    {"family": "Sahel", "label": "ساحل", "regular": "sahel/Sahel.woff2", "bold": "sahel/Sahel-Bold.woff2"},
    {"family": "Estedad", "label": "استعداد", "regular": "estedad/Estedad.woff2", "bold": "estedad/Estedad-Bold.woff2"},
    {"family": "Parastoo", "label": "پرستو", "regular": "parastoo/Parastoo.woff2", "bold": "parastoo/Parastoo-Bold.woff2"},
    {"family": "Gandom", "label": "گندم", "regular": "gandom/Gandom.woff2", "bold": None},
    {"family": "Tanha", "label": "تنها", "regular": "tanha/Tanha.woff2", "bold": None},
]


def file_outline(path):
    """ساختار یک فایل منبع، برای ساختن خودکار جلسه‌ها.

    Markdown: عنوان‌ها. PDF: فهرست مطالب داخل فایل.
    خروجی: {"unit": "heading" یا "page", "pages": تعداد صفحه, "entries": [{"level", "title", "page"}]}
    یا None اگر ساختاری پیدا نشد. فقط برای فایلی صدا زده می‌شود که کاربر انتخاب کرده یا برای درس ثبت شده است.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if not path.is_file():
        return None
    if suffix == ".md":
        item = {"source_type": "file", "source_path_or_url": str(path)}
        entries = [{"level": h["level"], "title": h["text"], "page": None} for h in markdown_headings(item, "")]
        return {"unit": "heading", "pages": None, "entries": entries} if entries else None
    if suffix == ".pdf":
        import pypdfium2 as pdfium
        try:
            doc = pdfium.PdfDocument(str(path))
        except Exception:
            return None
        try:
            entries = []
            for bookmark in doc.get_toc():
                page = bookmark.get_dest().get_index() if bookmark.get_dest() else None
                if page is not None:
                    entries.append({"level": bookmark.level + 1, "title": bookmark.get_title(), "page": page + 1})
            pages = len(doc)
        except Exception:
            return None
        finally:
            doc.close()
        return {"unit": "page", "pages": pages, "entries": entries} if entries else None
    return None
