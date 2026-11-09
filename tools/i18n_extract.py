"""متن‌های قابل ترجمهٔ برنامه را پیدا می‌کند و به static/i18n/keys.txt اضافه می‌کند.

    python tools/i18n_extract.py          متن‌های تازه را به انتهای keys.txt اضافه می‌کند
    python tools/i18n_extract.py --check  فقط بررسی می‌کند؛ اگر متن تازه‌ای باشد خطا می‌دهد

هر سطر keys.txt یک متن فارسی است و سطر همان شماره در هر فایل زبان، ترجمهٔ آن است.
متن تازه همیشه به انتها اضافه می‌شود تا ترتیب قبلی به هم نخورد. بعد ترجمهٔ آن را به
انتهای فایل هر زبان اضافه کنید. tests/test_i18n.py بررسی می‌کند چیزی جا نیفتاده باشد.
"""

import ast
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "static" / "i18n" / "keys.txt"
PERSIAN = re.compile(r"[؀-ۿ]")
# ثابت‌های بیرون از تابع که موقع استفاده ترجمه می‌شوند
CONSTANT_MODULES = {"database.py", "sources.py", "undo.py", "reports.py", "jalali.py", "exporter.py"}


def from_javascript():
    found = []
    for path in sorted((ROOT / "static" / "js").glob("*.js")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'\bt\(\s*("(?:[^"\\]|\\.)*")', text):
            found.append(json.loads(match.group(1)))
    return found


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        for name, value in attrs:
            if name in ("title", "placeholder", "aria-label") and value and PERSIAN.search(value):
                self.found.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", data).strip()
        if not self.skip and PERSIAN.search(text):
            self.found.append(text)


def from_template():
    page = _Page()
    page.feed((ROOT / "templates" / "index.html").read_text(encoding="utf-8"))
    return page.found


def from_python():
    found = []
    files = [p for p in ROOT.glob("*.py")] + list((ROOT / "routes").glob("*.py")) + list((ROOT / "services").glob("*.py"))
    for path in sorted(files):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_" and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.append(node.args[0].value)
        if path.name in CONSTANT_MODULES:
            for statement in tree.body:
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    for node in ast.walk(statement):
                        if isinstance(node, ast.Constant) and isinstance(node.value, str) and PERSIAN.search(node.value):
                            found.append(node.value)
    return found


def all_texts():
    seen = {}
    for text in from_template() + from_javascript() + from_python():
        seen.setdefault(text.replace("\n", "\\n"))
    return list(seen)


def main():
    existing = KEYS.read_text(encoding="utf-8").split("\n") if KEYS.exists() else []
    existing = [line for line in existing if line]
    new = [text for text in all_texts() if text not in set(existing)]
    if "--check" in sys.argv:
        if new:
            sys.exit("متن ترجمه‌نشده:\n" + "\n".join(new))
        return
    KEYS.write_text("\n".join(existing + new) + "\n", encoding="utf-8")
    print(f"{len(existing)} متن قبلی، {len(new)} متن تازه")


if __name__ == "__main__":
    main()
