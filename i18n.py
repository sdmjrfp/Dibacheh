"""زبان برنامه در سمت سرور.

متن اصلی برنامه فارسی است و خود متن فارسی کلید ترجمه است:
    _("این جلسه پیدا نشد.")
    _("{0} باید عدد باشد.", label)
ترجمه‌ها در static/i18n هستند: keys.txt همهٔ متن‌ها، و هر زبان یک فایل با همان ترتیب سطرها.
tools/i18n_extract.py متن‌های تازه را به انتهای keys.txt اضافه می‌کند.
"""

import sys
from contextvars import ContextVar
from pathlib import Path

# (نام به زبان خودش، جهت متن). ترتیب همان ترتیب نمایش در فهرست است.
LANGUAGES = {
    "fa": ("فارسی", "rtl"),
    "en": ("English", "ltr"),
    "zh": ("简体中文", "ltr"),
    "es": ("Español", "ltr"),
    "ar": ("العربية", "rtl"),
    "hi": ("हिन्दी", "ltr"),
    "pt": ("Português", "ltr"),
    "fr": ("Français", "ltr"),
    "ru": ("Русский", "ltr"),
    "id": ("Bahasa Indonesia", "ltr"),
    "de": ("Deutsch", "ltr"),
    "tr": ("Türkçe", "ltr"),
    "ja": ("日本語", "ltr"),
}

_FOLDER = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "static" / "i18n"
_language = ContextVar("language", default="fa")
_tables = {}


def set_language(code):
    _language.set(code if code in LANGUAGES else "fa")


def current():
    return _language.get()


def _lines(name):
    return (_FOLDER / f"{name}.txt").read_text(encoding="utf-8").split("\n")


def _table(code):
    if code not in _tables:
        try:
            keys = _lines("keys")
            values = _lines(code)
            _tables[code] = {k.replace("\\n", "\n"): v.replace("\\n", "\n") for k, v in zip(keys, values, strict=False) if v}
        except OSError:
            _tables[code] = {}
    return _tables[code]


def _(text, *args):
    """متن را به زبان فعلی برمی‌گرداند. ترجمه‌نشده = همان فارسی."""
    code = _language.get()
    if code != "fa":
        text = _table(code).get(text, text)
    for index, value in enumerate(args):
        text = text.replace("{%d}" % index, str(value))
    return text
