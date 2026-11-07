"""آیکون برنامه را از tools/icon.png به قالب هر سیستم تبدیل می‌کند (icns، ico یا png)."""

import sys
from pathlib import Path

from PIL import Image

SOURCE = Path(__file__).resolve().parent / "icon.png"


def main(target):
    image = Image.open(SOURCE)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    if target.endswith(".icns"):
        sizes += [(512, 512), (1024, 1024)]
    image.save(target, sizes=sizes)


if __name__ == "__main__":
    main(sys.argv[1])
