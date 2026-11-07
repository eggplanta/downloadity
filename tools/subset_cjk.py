"""
Builds the small Chinese font from the app texts
Run again after changing UI/i18n.py
Needs pyftsubset (fonttools) and Noto Sans CJK
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "UI"))

import i18n

SOURCE = "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"
# Noto Sans Mono CJK TC inside the collection
FONT_NUMBER = 8
OUTPUT = os.path.join(ROOT, "UI", "fonts", "NotoSansMonoCJKtc-subset.ttf")

chars = set("".join(i18n.all_texts()))
chars |= {chr(c) for c in range(0x20, 0x7F)}
chars |= set("♪▶♥…·›‹「」（）：；，。！？、／")

with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write("".join(sorted(chars)))

subprocess.run(
    [
        "pyftsubset", SOURCE,
        f"--font-number={FONT_NUMBER}",
        f"--text-file={f.name}",
        f"--output-file={OUTPUT}",
        "--layout-features=*",
        "--no-hinting",
    ],
    check=True,
)
os.remove(f.name)
print(f"{OUTPUT}: {os.path.getsize(OUTPUT) // 1024} KB, {len(chars)} chars")
