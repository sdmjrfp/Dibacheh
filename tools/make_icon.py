"""آیکون برنامه را از tools/icon.png به قالب هر سیستم تبدیل می‌کند (icns، ico یا png).

    python tools/make_icon.py <فایل خروجی>
    python tools/make_icon.py --from-logo     tools/icon.png و تصویرهای وابسته را از docs/logo.png می‌سازد

اگر لوگو عوض شد، فقط docs/logo.png را عوض کنید و دستور دوم را اجرا کنید.
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "icon.png"
LOGO = ROOT / "docs" / "logo.png"


def background(logo):
    """رنگ زمینهٔ لوگو، از گوشهٔ تصویر"""
    return logo.convert("RGBA").getpixel((2, 2))


def _fit(logo, box):
    """لوگو بدون تغییر نسبت، در یک کادر"""
    scale = min(box[0] / logo.width, box[1] / logo.height)
    return logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)


def trim(logo, color):
    """حاشیهٔ خالی دور لوگو برداشته می‌شود تا لوگو وسط آیکون و تا جای ممکن بزرگ باشد"""
    plain = Image.new("RGBA", logo.size, color)
    box = ImageChops.difference(logo, plain).convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
    return logo.crop(box) if box else logo


def build_from_logo():
    original = Image.open(LOGO).convert("RGBA")
    color = background(original)
    logo = trim(original, color)

    # آیکون: کاشی گرد با کمی فاصله از لبه، مثل آیکون‌های دیگر macOS
    icon = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(icon).rounded_rectangle((100, 100, 924, 924), radius=185, fill=color)
    inner = _fit(logo, (700, 700))
    icon.alpha_composite(inner, ((1024 - inner.width) // 2, (1024 - inner.height) // 2))
    icon.save(SOURCE)

    # آیکون زبانهٔ مرورگر
    icon.resize((256, 256), Image.LANCZOS).save(ROOT / "static" / "icon.png")

    # تصویر اشتراک‌گذاری لینک ریپو در GitHub (Social preview): 1280 در 640
    social = Image.new("RGBA", (1280, 640), color)
    inner = _fit(logo, (900, 420))
    social.alpha_composite(inner, ((1280 - inner.width) // 2, (640 - inner.height) // 2))
    social.convert("RGB").save(ROOT / "docs" / "social-preview.png")


def main(target):
    image = Image.open(SOURCE)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    if target.endswith(".icns"):
        sizes += [(512, 512), (1024, 1024)]
    image.save(target, sizes=sizes)


if __name__ == "__main__":
    if sys.argv[1] == "--from-logo":
        build_from_logo()
    else:
        main(sys.argv[1])
