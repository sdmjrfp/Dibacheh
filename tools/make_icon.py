"""آیکون Dibacheh.app را می‌سازد: مربع گرد سبز با حرف «د»."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
ROOT = Path(__file__).resolve().parent.parent


def main(target):
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((64, 64, SIZE - 64, SIZE - 64), radius=200, fill="#2f6f5e")
    for path, size in ((ROOT / "static/vendor/vazirmatn/Vazirmatn-Variable.woff2", 620),
                       (Path("/System/Library/Fonts/Supplemental/Arial.ttf"), 620)):
        try:
            font = ImageFont.truetype(str(path), size)
            break
        except OSError:
            font = None
    draw.text((SIZE / 2, SIZE / 2), "د", font=font, fill="white", anchor="mm")
    image.save(target, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])


if __name__ == "__main__":
    main(sys.argv[1])
