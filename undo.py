"""برگرداندن و بازگرداندن تغییرها (Undo و Redo).

قبل از هر تغییر، یک کپی فشرده از دیتابیس در حافظه نگه داشته می‌شود.
«برگرداندن» آخرین کپی را سر جایش می‌گذارد. تا 20 مرحله نگه داشته می‌شود،
و فقط تا وقتی برنامه باز است (با بستن برنامه پاک می‌شود).
"""

import sqlite3
import zlib
from collections import deque

from i18n import _

UNDO_LIMIT = 20
stack = deque(maxlen=UNDO_LIMIT)  # هر عضو: (متن تغییر، کپی دیتابیس). قدیمی‌ترین خودش کنار می‌رود
redo_stack = []                   # تغییرهای برگردانده‌شده؛ با هر تغییر تازه خالی می‌شود

# نام هر مسیر تغییردهنده و متنی که روی دکمهٔ برگرداندن نشان داده می‌شود
UNDO_LABELS = {
    "api_add_item": "افزودن درس",
    "api_update_item": "ویرایش درس",
    "api_split_item": "تغییر تقسیم‌بندی",
    "api_delete_item": "حذف درس",
    "api_reset_item": "برگرداندن درس",
    "api_reorder": "جابه‌جایی در صف",
    "api_unpin_item": "برگشت درس به چینش خودکار",
    "api_remove_reviews": "حذف مرورهای درس",
    "api_restore_reviews": "برگرداندن مرورهای درس",
    "api_update_session": "ویرایش جلسه",
    "api_move_task": "جابه‌جایی کار",
    "api_set_day": "تغییر سقف روز",
    "api_task_done": "ثبت انجام کار",
    "api_task_undone": "انجام‌نشده کردن کار",
    "api_missed_dismiss": "حذف کار انجام‌نشده",
    "api_missed_done": "ثبت انجام کار عقب‌افتاده",
    "api_set_day_range": "تعطیلی چندروزه",
    "api_archive_item": "بایگانی درس",
    "api_bulk_add": "افزودن گروهی",
    "api_restore_backup": "برگرداندن backup",
    "api_import_data": "ورود داده‌ها",
    "api_add_category": "افزودن دسته",
    "api_rename_category": "تغییر نام دسته",
    "api_delete_category": "حذف دسته",
    "api_reorder_categories": "جابه‌جایی دسته‌ها",
    "api_add_type": "ساختن نوع کار",
    "api_update_type": "ویرایش نوع کار",
    "api_delete_type": "حذف نوع کار",
    "api_add_font": "افزودن فونت",
    "api_remove_font": "حذف فونت",
    "api_settings": "تغییر تنظیمات",
}


def snapshot(conn):
    """کپی فشردهٔ دیتابیس. فشرده‌سازی حجم هر مرحله را چند برابر کم می‌کند."""
    return zlib.compress(conn.serialize(), 1)


def restore(conn, data):
    """دیتابیس را به یک کپی برمی‌گرداند."""
    source = sqlite3.connect(":memory:")
    try:
        source.deserialize(zlib.decompress(data))
        source.backup(conn)
    finally:
        source.close()


def info():
    """وضعیت دکمه‌های برگرداندن و بازگرداندن، برای صفحه."""
    return {"count": len(stack), "label": _(stack[-1][0]) if stack else None,
            "redo_count": len(redo_stack), "redo_label": _(redo_stack[-1][0]) if redo_stack else None}
