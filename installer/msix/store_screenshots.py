"""Screenshots for the Microsoft Store listing (installer/msix/STORE_LISTING.md), from the window pictures in docs/img.

    python installer/msix/store_screenshots.py

Writes build/store/<language>/<n>-<page>.png. Partner Center wants PNG files of at least 1366 x 768: smaller pictures
are centred on a 1920 x 1080 background of the window's own color. Needs Pillow (pip install pillow).
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LANGS = ["en", "fr", "es", "de", "it", "pt"]
SHOTS = ["clock", "look", "timer", "font"]  # in the listing's order
MIN_W, MIN_H = 1366, 768


def screenshot(src, dest):
    im = Image.open(src).convert("RGBA")
    background = im.getpixel((im.width // 2, 2))[:3]  # the window's color, along its top edge
    if im.width >= MIN_W and im.height >= MIN_H:
        size = im.size
    else:
        size = (max(1920, im.width), max(1080, im.height))
    canvas = Image.new("RGBA", size, background + (255,))
    canvas.alpha_composite(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    canvas.convert("RGB").save(dest, optimize=True)
    return size


def main():
    for lang in LANGS:
        out = os.path.join(ROOT, "build", "store", lang)
        os.makedirs(out, exist_ok=True)
        for i, shot in enumerate(SHOTS, 1):
            dest = os.path.join(out, f"{i}-{shot}.png")
            w, h = screenshot(os.path.join(ROOT, "docs", "img", f"window-{shot}-{lang}.webp"), dest)
            print(f"{dest}  {w}x{h}")


if __name__ == "__main__":
    main()
