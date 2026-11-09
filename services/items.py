"""درس‌ها و جلسه‌ها: ساختن، ویرایش، تقسیم‌بندی، وابستگی و صف."""

import re

import database
import leitner
import scheduler
import sources
from errors import NotFoundError, UserError
from i18n import _
from services.parsing import parse_date, positive_int
from services.state import item_status


def require_item(conn, item_id):
    item = database.get_item(conn, item_id)
    if item is None:
        raise NotFoundError()
    return item


def item_fields(data):
    """فیلدهای درس را از درخواست می‌خواند و بررسی می‌کند."""
    fields = {}
    if "title" in data:
        title = str(data["title"]).strip()
        if not title:
            raise UserError(_("عنوان درس خالی است."))
        fields["title"] = title
    if "item_type" in data:
        if data["item_type"] not in ("study", "routine"):
            raise UserError(_("نوع کار نامعتبر است."))
        fields["item_type"] = data["item_type"]
    if "variant" in data:
        if data["variant"] not in ("study", "project", "once"):
            raise UserError(_("گونهٔ کار نامعتبر است."))
        fields["variant"] = data["variant"]
        if data["variant"] != "study":
            fields["no_reviews"] = True
    if "category_id" in data:
        fields["category_id"] = data["category_id"] or None
    if "is_active" in data:
        fields["is_active"] = bool(data["is_active"])
    if "color" in data:
        try:
            fields["color"] = database.clean_color(data["color"])
        except ValueError as error:
            raise UserError(str(error))
    if "max_new_sessions_per_day" in data:
        fields["max_new_sessions_per_day"] = positive_int(data["max_new_sessions_per_day"], _("سرعت"))
    if "review_ratio" in data:
        ratio = data["review_ratio"] or None
        if ratio is not None:
            try:
                leitner.parse_ratio(ratio)
            except (ValueError, ZeroDivisionError):
                raise UserError(_("نسبت مرور نامعتبر است. مثال: 1/3 یا 0.5"))
        fields["review_ratio"] = ratio
    if "review_intervals" in data:
        intervals = data["review_intervals"] or None
        if intervals is not None:
            intervals = [positive_int(x, _("فاصلهٔ لایتنر")) for x in intervals]
        fields["review_intervals"] = intervals
    if "routine_weekdays" in data:
        days = data["routine_weekdays"] or None
        if days is not None:
            days = sorted({int(x) for x in days if 0 <= int(x) <= 6})
        fields["routine_weekdays"] = days or None
    for key in ("start_date", "target_date"):
        if key in data:
            fields[key] = parse_date(data[key])
    if "section_unit" in data:
        if data["section_unit"] not in ("page", "time", "heading", "text"):
            raise UserError(_("نوع بخش نامعتبر است."))
        fields["section_unit"] = data["section_unit"]
    for key in ("range_start", "range_end"):
        if key in data:
            fields[key] = str(data[key]).strip() or None
    if "source_type" in data:
        if data["source_type"] not in ("vault", "file", "url", "none"):
            raise UserError(_("نوع منبع نامعتبر است."))
        fields["source_type"] = data["source_type"]
    if "source_path_or_url" in data:
        fields["source_path_or_url"] = str(data["source_path_or_url"] or "").strip() or None
    if fields.get("source_type") == "url" and fields.get("source_path_or_url"):
        if not sources.is_web_url(fields["source_path_or_url"]):
            raise UserError(_("لینک باید با http:// یا https:// شروع شود."))
    if fields.get("source_type") == "none":
        fields["source_path_or_url"] = None
    return fields


def _apply_auto_split(conn, item_id):
    """بازهٔ باقی‌ماندهٔ درس را خودکار بین جلسه‌های خوانده‌نشده تقسیم می‌کند."""
    item = database.get_item(conn, item_id)
    sessions = database.list_sessions(conn, item_id)
    kept = [s for s in sessions if s["status"] != "unread"]
    unread = [s for s in sessions if s["status"] == "unread"]
    if item["section_unit"] not in ("page", "time") or not unread:
        return
    start = item["range_start"]
    last_kept = max(kept, key=lambda s: s["sequence"], default=None)
    if last_kept and last_kept.get("section_end"):
        if item["section_unit"] == "page":
            start = str(int(last_kept["section_end"]) + 1)
        else:
            start = last_kept["section_end"]
    try:
        parts = sources.split_range(item["section_unit"], start, item["range_end"], len(unread))
    except ValueError:
        raise UserError(_("بازهٔ درس نامعتبر است."))
    if parts is None:
        return
    for s, (a, b) in zip(sorted(unread, key=lambda s: s["sequence"]), parts, strict=True):
        database.update_session(conn, s["id"], section_start=a, section_end=b)


def _save_requires(conn, item_id, requires):
    """وابستگی‌های یک درس را بررسی و ذخیره می‌کند: فقط درس‌های موجود و بدون دور."""
    if not isinstance(requires, list):
        raise UserError(_("وابستگی‌ها نامعتبرند."))
    items = {i["id"]: i for i in database.list_items(conn)}
    cleaned = []
    for req in requires:
        other = req.get("id")
        until = req.get("until", "read")
        if other not in items or other == item_id or items[other]["item_type"] != "study":
            raise UserError(_("پیش‌نیاز باید یک درس دیگر باشد."))
        if until not in ("read", "finished"):
            raise UserError(_("نوع وابستگی نامعتبر است."))
        cleaned.append({"id": other, "until": until})
    # اگر پیش‌نیازها خودشان (مستقیم یا غیرمستقیم) به این درس وابسته باشند، هیچ‌کدام شروع نمی‌شوند
    graph = {k: [r["id"] for r in v] for k, v in database.list_dependencies(conn).items()}
    stack = [r["id"] for r in cleaned]
    seen = set()
    while stack:
        current = stack.pop()
        if current == item_id:
            raise UserError(_("این وابستگی یک دور می‌سازد: دو درس منتظر هم می‌مانند."))
        if current not in seen:
            seen.add(current)
            stack.extend(graph.get(current, []))
    database.set_dependencies(conn, item_id, cleaned)


def _apply_sections(conn, item_id, unit, sections):
    """بخش جلسه‌های خوانده‌نشده را از فهرست بخش‌ها (عنوان‌های نوت یا فصل‌های PDF) پر می‌کند."""
    unread = [s for s in database.list_sessions(conn, item_id) if s["status"] == "unread"]
    for session, section in zip(unread, sections, strict=False):
        database.update_session(conn, session["id"], section_start=str(section.get("start") or "") or None,
                                section_end=str(section.get("end") or "") or None,
                                section_label=str(section.get("title") or ""))
    database.update_item(conn, item_id, section_unit=unit)


def create_item(conn, data, day):
    defaults = database.get_settings(conn)["new_item_defaults"]
    count = positive_int(data.get("session_count", 1), _("تعداد جلسه"))
    minutes = positive_int(data.get("session_minutes", defaults["session_minutes"]), _("زمان جلسه"))
    fields = item_fields(data)
    if "title" not in fields:
        raise UserError(_("عنوان درس خالی است."))
    title = fields.pop("title")
    # نوع کار ساخت کاربر: رفتارش (درس یا روتین) از خود نوع می‌آید
    if data.get("custom_type_id"):
        custom = database.get_type(conn, data["custom_type_id"])
        if custom is None:
            raise UserError(_("نوع کار پیدا نشد."))
        fields["custom_type_id"] = custom["id"]
        fields["item_type"] = custom["behavior"]
    fields.setdefault("category_id", defaults.get("category_id"))
    fields.setdefault("max_new_sessions_per_day", defaults.get("max_new_sessions_per_day", 1))
    # first_date: وقتی درس از روی یک روز تقویم اضافه می‌شود
    first_date = parse_date(data.get("first_date"))
    if fields.get("item_type") == "routine":
        fields["start_date"] = fields.get("start_date") or first_date or day
    if "color" not in fields:
        used = len(database.list_items(conn))
        fields["color"] = database.SOURCE_PALETTE[used % len(database.SOURCE_PALETTE)]
    sections = data.get("sections") or []
    if sections:
        count = len(sections)
    item_id = database.add_item(conn, title, count, minutes, **fields)
    _apply_auto_split(conn, item_id)
    if sections:
        _apply_sections(conn, item_id, fields.get("section_unit", "text"), sections)
    if data.get("requires"):
        _save_requires(conn, item_id, data["requires"])
    if first_date and fields.get("item_type") != "routine":
        # جلسهٔ اول دستی به همان روز می‌رود؛ بقیهٔ جلسه‌ها پشت سرش می‌آیند
        first = database.list_sessions(conn, item_id)[0]
        database.update_session(conn, first["id"], read_manual_date=max(first_date, day))


def update_item(conn, item_id, data):
    require_item(conn, item_id)
    fields = item_fields(data)
    database.update_item(conn, item_id, **fields)
    if "requires" in data:
        _save_requires(conn, item_id, data["requires"])
    if {"range_start", "range_end", "section_unit"} & set(fields):
        _apply_auto_split(conn, item_id)


def remove_reviews(conn, item_id):
    """همهٔ مرورهای یک درس حذف می‌شود: مرورهای باقی‌مانده دیگر چیده نمی‌شوند
    و از این به بعد جلسه‌ها با خواندن تمام می‌شوند. سابقهٔ کارهای انجام‌شده می‌ماند."""
    item = require_item(conn, item_id)
    if item["item_type"] != "study":
        raise UserError(_("این کار مرور ندارد."))
    database.update_item(conn, item_id, no_reviews=True)
    for session in database.list_sessions(conn, item_id):
        if session["status"] == "reviewing":
            database.update_session(conn, session["id"], status="finished", next_review_on=None, review_manual_date=None)
        elif session["review_manual_date"]:
            database.update_session(conn, session["id"], review_manual_date=None)


def restore_reviews(conn, item_id):
    """مرورها دوباره فعال می‌شوند. جلسه‌ای که همهٔ مرورهایش را نگذرانده، از همان جعبه ادامه می‌دهد."""
    item = require_item(conn, item_id)
    database.update_item(conn, item_id, no_reviews=False)
    intervals = leitner.intervals_for({**item, "no_reviews": False}, database.get_settings(conn))
    for session in database.list_sessions(conn, item_id):
        box = session["leitner_box"] or 0
        if session["status"] == "finished" and session["read_at"] and box < len(intervals):
            database.update_session(conn, session["id"], status="reviewing", leitner_box=max(box, 1))


def split_item(conn, item_id, data):
    """تغییر تقسیم‌بندی: جلسه‌های انجام‌شده می‌مانند، بقیه دوباره ساخته می‌شوند."""
    require_item(conn, item_id)
    sections = data.get("sections") or []
    count = len(sections) or positive_int(data.get("session_count"), _("تعداد جلسهٔ باقی‌مانده"))
    minutes = data.get("session_minutes")
    minutes = positive_int(minutes, _("زمان جلسه")) if minutes not in (None, "") else None
    _kept, new = scheduler.resplit_remaining(database.list_sessions(conn, item_id), count, minutes)
    database.replace_unread_sessions(conn, item_id, new)
    _apply_auto_split(conn, item_id)
    if sections:
        _apply_sections(conn, item_id, data.get("section_unit", "text"), sections)


def archive_item(conn, item_id, archived):
    """درس تمام‌شده از فهرست اصلی پنهان می‌شود. سابقه‌اش می‌ماند."""
    require_item(conn, item_id)
    if archived and item_status(database.list_sessions(conn, item_id)) != "finished":
        raise UserError(_("فقط درس تمام‌شده بایگانی می‌شود."))
    database.update_item(conn, item_id, archived=archived)


def bulk_add(conn, data):
    """چند درس با هم. هر خط: عنوان، تعداد جلسه، زمان جلسه (دو عدد آخر اختیاری‌اند)."""
    defaults = database.get_settings(conn)["new_item_defaults"]
    rows = []
    for number, line in enumerate(str(data.get("text", "")).splitlines(), start=1):
        parts = [p.strip() for p in re.split(_("[،,|\\t]"), line) if p.strip()]
        if not parts:
            continue
        digits = [_latin_digits(p) for p in parts[1:]]
        if any(not d.isdigit() or int(d) < 1 for d in digits) or len(digits) > 2:
            raise UserError(_("خط {0}: بعد از عنوان فقط تعداد جلسه و زمان جلسه بیاید.", number))
        rows.append((parts[0], int(digits[0]) if digits else 1,
                     int(digits[1]) if len(digits) > 1 else defaults["session_minutes"]))
    if not rows:
        raise UserError(_("هیچ درسی نوشته نشده است."))
    fields = {"max_new_sessions_per_day": defaults.get("max_new_sessions_per_day", 1)}
    if data.get("category_id"):
        fields["category_id"] = data["category_id"]
    if data.get("custom_type_id"):
        custom = database.get_type(conn, data["custom_type_id"])
        if custom is None:
            raise UserError(_("نوع کار پیدا نشد."))
        fields.update(custom_type_id=custom["id"], item_type=custom["behavior"])
    palette = database.SOURCE_PALETTE
    used = len(database.list_items(conn))
    for offset, (title, count, minutes) in enumerate(rows):
        database.add_item(conn, title, count, minutes, color=palette[(used + offset) % len(palette)], **fields)


def _latin_digits(text):
    return text.translate(str.maketrans(_("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"), "01234567890123456789"))


def reorder(conn, data):
    """ترتیب تازهٔ صف را ذخیره می‌کند. خروجی: چند جلسهٔ دستی آزاد شد."""
    ids = data.get("ids")
    existing = {i["id"] for i in database.list_items(conn)}
    if not isinstance(ids, list) or set(ids) != existing or len(ids) != len(existing):
        raise UserError(_("ترتیب صف نامعتبر است."))
    database.reorder_items(conn, ids)
    # درسی که کاربر در صف جابه‌جا کرد، از این به بعد طبق جای تازه‌اش در صف چیده می‌شود:
    # خواندن‌هایی از همین درس که قبلاً دستی به روز خاصی برده شده بودند، آزاد می‌شوند.
    # (وگرنه کار دستی سر روز انتخابی‌اش می‌ماند و جابه‌جایی صف روی تقویم اثری نمی‌گذاشت.)
    moved = data.get("moved_id")
    return database.clear_manual_dates(conn, moved, reviews=False) if moved in existing else 0


def update_session(conn, session_id, data):
    if database.get_session(conn, session_id) is None:
        raise NotFoundError()
    fields = {}
    for key in ("section_label", "section_start", "section_end"):
        if key in data:
            fields[key] = str(data[key] or "").strip() or None
    if "section_label" in fields:
        fields["section_label"] = fields["section_label"] or ""
    if "note" in data:
        fields["note"] = str(data["note"] or "").strip()[:5000]
    if "minutes" in data:
        fields["minutes"] = positive_int(data["minutes"], _("زمان جلسه"))
    if "review_minutes_override" in data:
        value = data["review_minutes_override"]
        fields["review_minutes_override"] = None if value in (None, "") else positive_int(value, _("زمان مرور"))
    database.update_session(conn, session_id, **fields)
