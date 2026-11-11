#!/usr/bin/env python3
"""Fetch placeholder images from placehold.co and write responsive WebP widths into images/.

    pip install pillow   # once
    python3 tools/make_images.py

Reads src/data/images.json. For each entry it downloads one full-size WebP, then
writes <name>.webp and <name>.avif (full size) and -<w>w.webp / -<w>w.avif for each smaller width.
Pages use <picture>: AVIF first, WebP as the fallback.
Swap the placeholders for real photos by dropping a file at images/<dir>/<name>.webp
(or .jpg/.png) at the full size listed in images.json and re-running with --no-fetch.
The width list must match the files on disk: a srcset that names a missing file is ignored.
"""
import io, json, sys, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FETCH = "--no-fetch" not in sys.argv
COLORS = ["1f5f5b", "6927da", "b54708", "3b4a6b", "18794e"]

for i, e in enumerate(json.loads((ROOT / "src/data/images.json").read_text())):
    folder = ROOT / "images" / e["dir"]
    folder.mkdir(parents=True, exist_ok=True)
    full = folder / f"{e['name']}.webp"
    if FETCH or not full.exists():
        text = urllib.parse.quote(e["text"])
        url = f"https://placehold.co/{e['w']}x{e['h']}/{COLORS[i % len(COLORS)]}/ffffff.webp?text={text}"
        with urllib.request.urlopen(url, timeout=30) as r:
            full.write_bytes(r.read())
    im = Image.open(full).convert("RGB")
    im.save(full, "WEBP", quality=80, method=6)
    im.save(full.with_suffix(".avif"), "AVIF", quality=55)
    for w in e["widths"]:
        if w >= e["w"]:
            continue
        h = round(e["h"] * w / e["w"])
        small = im.resize((w, h), Image.LANCZOS)
        small.save(folder / f"{e['name']}-{w}w.webp", "WEBP", quality=80, method=6)
        small.save(folder / f"{e['name']}-{w}w.avif", "AVIF", quality=55)
    print(f"ok {e['dir']}/{e['name']}")
# Open Graph needs PNG or JPG, so the social card is fetched separately.
og = ROOT / "images" / "og-default.png"
if FETCH:
    with urllib.request.urlopen("https://placehold.co/1200x630/1f5f5b/ffffff.png?text=Visit+Joburg", timeout=30) as r:
        og.write_bytes(r.read())
print("ok og-default.png")
