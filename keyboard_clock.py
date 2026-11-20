#!/usr/bin/env python3
"""Keyboard Clock: shows the time on the per-key RGB lighting of your keyboard when you step away.

This file is the engine: keyboard layouts, digits and scrolling text drawn on the keys, colors and
backgrounds, transitions, triggers (idle, lock, hotkey, full-screen apps, night) and the Logitech
G HUB back-end. Zero dependencies: Python 3.8+ standard library and Windows.

    python keyboard_clock.py                 run the clock (Ctrl+C to stop)
    python keyboard_clock.py --demo          play every display mode and look on the keyboard, then exit
    python keyboard_clock.py --preview a.png draw the demo scenes into a picture (no keyboard needed)
    python keyboard_clock.py --stop          stop the clock running in the background
    python keyboard_clock.py --bench         measure how fast the keyboard takes colors
"""

import argparse
import colorsys
import ctypes
import datetime as dt
import functools
import hashlib
import json
import math
import os
import re
import struct
import sys
import threading
import time
import unicodedata
import zlib
from ctypes import wintypes

__version__ = "0.1.0"
APP = "Keyboard Clock"
APP_ID = "KeyboardClock"
REPO_URL = "https://github.com/Ilyomix/keyboard-clock"
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_ID)
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LOG_PATH = os.path.join(DATA_DIR, "keyboard-clock.log")
STOP_EVENT = "Local\\KeyboardClock.Stop"

_log_lock = threading.Lock()


def log(msg):
    if sys.stdout is not None:
        try:
            print(msg, flush=True)
        except (OSError, ValueError):
            pass
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with _log_lock, open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Keys: HID usage (physical position, named after the US layout, so it holds for AZERTY, QWERTZ…)
# and Logitech G HUB key code (the LED SDK's KeyName, a scan code).
# ---------------------------------------------------------------------------
KEY_CODES = {
    "Esc": (0x29, 0x01), "F11": (0x44, 0x57), "F12": (0x45, 0x58),
    "PrtSc": (0x46, 0x137), "ScrLk": (0x47, 0x46), "Pause": (0x48, 0x145),
    "`": (0x35, 0x29), "0": (0x27, 0x0B), "-": (0x2D, 0x0C), "=": (0x2E, 0x0D), "Backspace": (0x2A, 0x0E),
    "Ins": (0x49, 0x152), "Home": (0x4A, 0x147), "PgUp": (0x4B, 0x149),
    "Tab": (0x2B, 0x0F), "[": (0x2F, 0x1A), "]": (0x30, 0x1B), "\\": (0x31, 0x2B),
    "Del": (0x4C, 0x153), "End": (0x4D, 0x14F), "PgDn": (0x4E, 0x151),
    "Caps": (0x39, 0x3A), ";": (0x33, 0x27), "'": (0x34, 0x28), "#": (0x32, 0x2B), "Enter": (0x28, 0x1C),
    "LShift": (0xE1, 0x2A), "<": (0x64, 0x56), ",": (0x36, 0x33), ".": (0x37, 0x34), "/": (0x38, 0x35),
    "RShift": (0xE5, 0x36), "Up": (0x52, 0x148),
    "LCtrl": (0xE0, 0x1D), "LWin": (0xE3, 0x15B), "LAlt": (0xE2, 0x38), "Space": (0x2C, 0x39),
    "RAlt": (0xE6, 0x138), "RWin": (0xE7, 0x15C), "Menu": (0x65, 0x15D), "RCtrl": (0xE4, 0x11D),
    "Left": (0x50, 0x14B), "Down": (0x51, 0x150), "Right": (0x4F, 0x14D),
    "NumLock": (0x53, 0x45), "KP/": (0x54, 0x135), "KP*": (0x55, 0x37), "KP-": (0x56, 0x4A), "KP+": (0x57, 0x4E),
    "KP7": (0x5F, 0x47), "KP8": (0x60, 0x48), "KP9": (0x61, 0x49), "KP4": (0x5C, 0x4B), "KP5": (0x5D, 0x4C),
    "KP6": (0x5E, 0x4D), "KP1": (0x59, 0x4F), "KP2": (0x5A, 0x50), "KP3": (0x5B, 0x51), "KPEnter": (0x58, 0x11C),
    "KP0": (0x62, 0x52), "KP.": (0x63, 0x53),
}
KEY_CODES.update({f"F{i}": (0x39 + i, 0x3A + i) for i in range(1, 11)})
KEY_CODES.update({str(i): (0x1D + i, 0x01 + i) for i in range(1, 10)})
for _row, _first in (("QWERTYUIOP", 0x10), ("ASDFGHJKL", 0x1E), ("ZXCVBNM", 0x2C)):
    for _i, _c in enumerate(_row):
        KEY_CODES[_c] = (ord(_c) - ord("A") + 0x04, _first + _i)
LOGITECH_LOGO = 0xFFFF1

ROW_YS = (0.0, 1.5, 2.5, 3.5, 4.5, 5.5)          # function row, numbers, top, home, bottom letters, space
MAIN_W = 15.0                                     # width of the main block (keys 0-15), digits and text live there
MODELS = ("tkl-iso", "tkl-ansi", "full-iso", "full-ansi")


def model_keys(name):
    """[(key, x, y, w, h)] in key units for 'tkl-iso', 'tkl-ansi', 'full-iso' or 'full-ansi'."""
    full, iso = name.startswith("full"), name.endswith("iso")
    keys = []

    def put(key, x, y, w=1.0, h=1.0):
        keys.append((key, float(x), float(y), float(w), float(h)))

    def run(names, x, y):
        for i, n in enumerate(names):
            put(n, x + i, y)

    put("Esc", 0, 0)
    run(["F1", "F2", "F3", "F4"], 2, 0)
    run(["F5", "F6", "F7", "F8"], 6.5, 0)
    run(["F9", "F10", "F11", "F12"], 11, 0)
    run(["PrtSc", "ScrLk", "Pause"], 15.25, 0)
    put("`", 0, 1.5)
    run(list("1234567890") + ["-", "="], 1, 1.5)
    put("Backspace", 13, 1.5, 2)
    run(["Ins", "Home", "PgUp"], 15.25, 1.5)
    put("Tab", 0, 2.5, 1.5)
    run(list("QWERTYUIOP") + ["[", "]"], 1.5, 2.5)
    put("Enter" if iso else "\\", 13.5, 2.5, 1.5)        # ISO: top half of the tall Enter
    run(["Del", "End", "PgDn"], 15.25, 2.5)
    put("Caps", 0, 3.5, 1.75)
    run(list("ASDFGHJKL") + [";", "'"], 1.75, 3.5)
    if iso:
        put("#", 12.75, 3.5)
        put("Enter", 13.75, 3.5, 1.25)
        put("LShift", 0, 4.5, 1.25)
        put("<", 1.25, 4.5)
    else:
        put("Enter", 12.75, 3.5, 2.25)
        put("LShift", 0, 4.5, 2.25)
    run(list("ZXCVBNM") + [",", ".", "/"], 2.25, 4.5)
    put("RShift", 12.25, 4.5, 2.75)
    put("Up", 16.25, 4.5)
    for k, x, w in (("LCtrl", 0, 1.25), ("LWin", 1.25, 1.25), ("LAlt", 2.5, 1.25), ("Space", 3.75, 6.25),
                    ("RAlt", 10, 1.25), ("RWin", 11.25, 1.25), ("Menu", 12.5, 1.25), ("RCtrl", 13.75, 1.25)):
        put(k, x, 5.5, w)
    run(["Left", "Down", "Right"], 15.25, 5.5)
    if full:
        run(["NumLock", "KP/", "KP*", "KP-"], 18.5, 1.5)
        run(["KP7", "KP8", "KP9"], 18.5, 2.5)
        put("KP+", 21.5, 2.5, 1, 2)
        run(["KP4", "KP5", "KP6"], 18.5, 3.5)
        run(["KP1", "KP2", "KP3"], 18.5, 4.5)
        put("KPEnter", 21.5, 4.5, 1, 2)
        put("KP0", 18.5, 5.5, 2)
        put("KP.", 20.5, 5.5)
    return keys


class Model:
    """A keyboard layout: key rectangles, plus lookups used to place digits and text."""

    def __init__(self, name):
        if name not in MODELS:
            raise ValueError(f"unknown keyboard model {name!r}")
        self.name = name
        self.rects = model_keys(name)
        self.keys = list(dict.fromkeys(k for k, *_ in self.rects))
        self.width = max(x + w for _, x, _, w, _ in self.rects)
        self.height = 6.5
        self.center = {}
        for k, x, y, w, h in self.rects:
            self.center.setdefault(k, (x + w / 2, y + h / 2))
        # Main-block rectangles of the five rows that carry digits and text: (key, x0, x1, row, cx)
        self.grid = [(k, x, x + w, ROW_YS.index(y), x + w / 2)
                     for k, x, y, w, h in self.rects if y in ROW_YS[:5] and x < MAIN_W]
        self.has_numpad = "KP5" in self.center

    def key_at(self, row, cx, tol=0.3):
        """Key of `row` (0-5) whose centre is within `tol` of `cx`, or None."""
        y = ROW_YS[row]
        for k, x, ky, w, h in self.rects:
            if ky == y and abs(x + w / 2 - cx) <= tol:
                return k
        return None


def default_model():
    """ANSI for US English keyboard layouts, ISO otherwise; tenkeyless unless the user says otherwise."""
    try:
        hkl = ctypes.windll.user32.GetKeyboardLayout(0) & 0xFFFF
    except (AttributeError, OSError):
        hkl = 0x0409
    return "tkl-ansi" if hkl in (0x0409, 0x0C09, 0x1009, 0x1409, 0x4009) else "tkl-iso"


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
BLACK = (0.0, 0.0, 0.0)


def hex_color(value, default=None):
    """'#RRGGBB', 'RRGGBB', 0xRRGGBB or [r, g, b] → (r, g, b) ints, else `default`."""
    if isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value):
        return tuple(max(0, min(255, int(round(v)))) for v in value)
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xFFFFFF:
        return ((value >> 16) & 255, (value >> 8) & 255, value & 255)
    if isinstance(value, str):
        s = value.strip().lstrip("#")
        if len(s) == 6:
            try:
                n = int(s, 16)
            except ValueError:
                return default
            return ((n >> 16) & 255, (n >> 8) & 255, n & 255)
    return default


def color_hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in c)


def gradient_at(stops, t):
    """Color at t (0-1) along evenly spaced stops, mixed in linear light so the middle stays bright."""
    if len(stops) == 1:
        return tuple(float(v) for v in stops[0])
    t = min(1.0, max(0.0, t)) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    f = t - i
    a, b = stops[i], stops[i + 1]
    return tuple(math.sqrt(a[k] ** 2 * (1 - f) + b[k] ** 2 * f) for k in range(3))


def hsv(h, s=1.0, v=1.0):
    return tuple(c * 255 for c in colorsys.hsv_to_rgb(h % 1.0, s, v))


def perceived(level):
    """0-1 perceived brightness → 0-1 LED power (gamma 2.2), so fades and dim levels look even."""
    return max(0.0, min(1.0, level)) ** 2.2


# Color through the day for the "time of day" style: (hour, color)
DAYTIME = ((0, (90, 0, 170)), (5, (200, 20, 70)), (7, (255, 100, 0)), (10, (255, 190, 90)),
           (13, (0, 200, 255)), (17, (255, 140, 0)), (20, (230, 0, 90)), (22, (120, 0, 200)), (24, (90, 0, 170)))


def daytime_color(wall):
    h = wall.hour + wall.minute / 60
    for (h0, c0), (h1, c1) in zip(DAYTIME, DAYTIME[1:]):
        if h0 <= h < h1:
            return gradient_at((c0, c1), (h - h0) / (h1 - h0))
    return tuple(float(v) for v in DAYTIME[0][1])


# ---------------------------------------------------------------------------
# Digits drawn key by key ("classic"): one string per row, # = lit key. Rows: function keys (4 cells:
# F1-F4 for the left digit, F5-F8 for the right one), then the number row (3 cells), the top letter
# row (4 cells, half a key to the left), the home row (4 cells) and the bottom letter row (3 cells).
# A tuple row is (left digit, right digit): F1-F4 sit over the number keys, F5-F8 are half a key off.
# A digit of 4 rows (the 0) leaves the function keys dark.
# ---------------------------------------------------------------------------
_BAR = ("###.", "####")
CLASSIC = {
    "0": ["###", "#..#", "#..#", "###"],
    "1": ["...#", "..#", "..#.", ".#..", "#.."],               # a single slash (F4 / F8 on top)
    "2": [_BAR, "..#", "####", "#...", "###"],
    "3": [_BAR, "..#", ".###", "...#", "###"],
    "4": [("#.#.", "#..#"), "#.#", "####", "...#", "..#"],
    "5": [_BAR, "#..", "####", "...#", "###"],
    "6": [(".#..", ".#.."), "#..", "####", "#..#", "###"],    # small hook (F2 / F6)
    "7": [_BAR, "..#", "..#.", ".#..", "#.."],
    "8": [".##.", "#.#", ".###", "#..#", "###"],              # small loop on top (F2-F3 / F6-F7)
    "9": [_BAR, "#.#", ".###", "...#", ".##"],                # curled tail
    " ": [],
}
CLASSIC_ROW_START = {1: 0.0, 2: -0.5, 3: -0.25, 4: 0.25}     # first cell of each row, from the digit's anchor
DIGIT_ANCHOR = (2.5, 7.5)                                     # centre of key "2" (left digit) and "7" (right)
F_KEYS = (("F1", "F2", "F3", "F4"), ("F5", "F6", "F7", "F8"))


def classic_keys(model, ch, pos):
    """Keys lit by character `ch` at position `pos` (0 = left digit, 1 = right digit)."""
    rows = CLASSIC.get(ch, [])
    keys = []
    if len(rows) == 5:
        f = rows[0][pos] if isinstance(rows[0], tuple) else rows[0]
        keys += [F_KEYS[pos][i] for i, p in enumerate(f) if p == "#"]
        rows = rows[1:]
    for r, line in enumerate(rows, start=1):
        for i, p in enumerate(line):
            if p == "#":
                k = model.key_at(r, DIGIT_ANCHOR[pos] + CLASSIC_ROW_START[r] + i)
                if k is None:
                    raise ValueError(f"digit {ch!r}: no key on row {r}, cell {i}")
                keys.append(k)
    return keys


# Custom digits (font editor): {"0": [[left digit keys], [right digit keys]], …}, keys by name.
FONT_SPLIT = 6.0                    # keys centred left of this belong to the left digit
FONT_RIGHT_END = 11.0               # the right digit stops before "[" / ";" / "/"


def digit_area(model, pos):
    """Keys a digit may use at `pos`: F1-F4 (left) or F5-F8 (right), and the number and letter rows on
    its side. The two areas never overlap, so the left and right digits can't collide."""
    keys = list(F_KEYS[pos])
    for k, x0, x1, row, cx in model.grid:
        if row and ((cx < FONT_SPLIT) if pos == 0 else (FONT_SPLIT <= cx < FONT_RIGHT_END)):
            keys.append(k)
    return list(dict.fromkeys(keys))


def classic_font(model):
    """The built-in digits as an editable font (the font editor starts from it)."""
    return {ch: [classic_keys(model, ch, 0), classic_keys(model, ch, 1)] for ch in "0123456789"}


def font_keys(model, ch, pos, custom=None):
    """Keys of digit `ch` at `pos`, from the custom font when it defines that digit."""
    if custom and ch in custom:
        area = set(digit_area(model, pos))
        return [k for k in custom[ch][pos] if k in area]
    return classic_keys(model, ch, pos)


def clean_font(v):
    out = {}
    if isinstance(v, dict):
        for ch in "0123456789":
            pair = v.get(ch)
            if isinstance(pair, list) and len(pair) == 2 and all(isinstance(p, list) for p in pair):
                out[ch] = [[k for k in dict.fromkeys(p) if isinstance(k, str) and k in KEY_CODES][:40] for p in pair]
    return out


# ---------------------------------------------------------------------------
# Pixel font for scrolling text: 5 rows (function keys to bottom letters), mostly 3 columns wide.
# ---------------------------------------------------------------------------
PIXEL = {
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#", "##", ".#", ".#", ".#"],
    "2": ["###", "..#", "###", "#..", "###"], "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"], "5": ["###", "#..", "###", "..#", "###"],
    "6": ["###", "#..", "###", "#.#", "###"], "7": ["###", "..#", "..#", ".#.", ".#."],
    "8": ["###", "#.#", "###", "#.#", "###"], "9": ["###", "#.#", "###", "..#", "###"],
    "A": [".#.", "#.#", "###", "#.#", "#.#"], "B": ["##.", "#.#", "##.", "#.#", "##."],
    "C": [".##", "#..", "#..", "#..", ".##"], "D": ["##.", "#.#", "#.#", "#.#", "##."],
    "E": ["###", "#..", "##.", "#..", "###"], "F": ["###", "#..", "##.", "#..", "#.."],
    "G": [".##", "#..", "#.#", "#.#", ".##"], "H": ["#.#", "#.#", "###", "#.#", "#.#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"], "J": ["..#", "..#", "..#", "#.#", ".#."],
    "K": ["#.#", "#.#", "##.", "#.#", "#.#"], "L": ["#..", "#..", "#..", "#..", "###"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"], "N": ["#..#", "##.#", "#.##", "#..#", "#..#"],
    "O": [".#.", "#.#", "#.#", "#.#", ".#."], "P": ["##.", "#.#", "##.", "#..", "#.."],
    "Q": [".#.", "#.#", "#.#", "##.", ".##"], "R": ["##.", "#.#", "##.", "#.#", "#.#"],
    "S": [".##", "#..", ".#.", "..#", "##."], "T": ["###", ".#.", ".#.", ".#.", ".#."],
    "U": ["#.#", "#.#", "#.#", "#.#", "###"], "V": ["#.#", "#.#", "#.#", "#.#", ".#."],
    "W": ["#...#", "#...#", "#.#.#", "##.##", "#...#"], "X": ["#.#", "#.#", ".#.", "#.#", "#.#"],
    "Y": ["#.#", "#.#", ".#.", ".#.", ".#."], "Z": ["###", "..#", ".#.", "#..", "###"],
    ":": [".", "#", ".", "#", "."], ".": [".", ".", ".", ".", "#"], ",": [".", ".", ".", "#", "#"],
    "-": ["...", "...", "###", "...", "..."], "+": ["...", ".#.", "###", ".#.", "..."],
    "/": ["..#", "..#", ".#.", "#..", "#.."], "·": [".", ".", "#", ".", "."], "'": ["#", "#", ".", ".", "."],
    "!": ["#", "#", "#", ".", "#"], "?": ["###", "..#", ".#.", "...", ".#."], "%": ["#.#", "..#", ".#.", "#..", "#.#"],
    "°": ["###", "#.#", "###", "...", "..."], "(": [".#", "#.", "#.", "#.", ".#"], ")": ["#.", ".#", ".#", ".#", "#."],
    "&": [".#.", "#.#", ".#.", "#.#", ".##"], "=": ["...", "###", "...", "###", "..."], "_": ["...", "...", "...", "...", "###"],
}
SCROLL_ROW_SHIFT = (0.0, 0.0, 0.5, 0.75, 1.25)   # each row follows the staggered key columns (1, Q, A, Z…)
EMPTY_COL = (0, 0, 0, 0, 0)


def plain_upper(text):
    text = text.replace("ß", "SS").replace("ẞ", "SS")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").upper()


def text_columns(runs):
    """[(text, role)] → one (bits, role, char number) per pixel column, a blank column between characters."""
    cols = []
    n = 0
    for text, role in runs:
        for ch in plain_upper(text):
            if ch == " ":
                cols += [(EMPTY_COL, role, n)] * 2
            else:
                g = PIXEL.get(ch) or PIXEL["?"]
                for c in range(len(g[0])):
                    cols.append((tuple(1 if g[r][c] == "#" else 0 for r in range(5)), role, n))
                cols.append((EMPTY_COL, role, n))
            n += 1
    while cols and cols[-1][0] == EMPTY_COL:
        cols.pop()
    return cols


def scroll_crisp(model, cols, offset, color_of):
    """Text moved by whole key columns: each key shows the pixel column(s) right under it, so the
    letters stay sharp (F5-F8, half a key off, and wide keys such as Tab included)."""
    out = {}
    for key, x0, x1, row, cx in model.grid:
        s = SCROLL_ROW_SHIFT[row]
        c0 = math.floor(x0 - s + 0.5)
        c1 = max(c0 + 1, math.floor(x1 - s + 0.5))
        hits = 0
        cr = cg = cb = 0.0
        for c in range(c0, c1):
            i = c - offset
            if 0 <= i < len(cols) and cols[i][0][row]:
                _, role, n = cols[i]
                col = color_of(role, n, cx)
                hits += 1
                cr += col[0]
                cg += col[1]
                cb += col[2]
        if hits:
            out[key] = (cr / hits, cg / hits, cb / hits, hits / (c1 - c0))
    return out


def scroll_spans(cols, offset):
    """Spans (row, x0, x1, role, n) for text whose first column sits at x = `offset` (key units)."""
    spans = []
    for c, (bits, role, n) in enumerate(cols):
        x = offset + c
        if x + 2 < 0 or x - 2 > MAIN_W:
            continue
        for r in range(5):
            if bits[r]:
                x0 = x + SCROLL_ROW_SHIFT[r]
                spans.append((r, x0, x0 + 1, role, n))
    return spans


# ---------------------------------------------------------------------------
# Dates in six languages
# ---------------------------------------------------------------------------
LANGS = ("en", "fr", "es", "de", "it", "pt")
WEEKDAYS = {
    "en": "MON TUE WED THU FRI SAT SUN", "fr": "LUN MAR MER JEU VEN SAM DIM",
    "es": "LUN MAR MIE JUE VIE SAB DOM", "de": "MO DI MI DO FR SA SO",
    "it": "LUN MAR MER GIO VEN SAB DOM", "pt": "SEG TER QUA QUI SEX SAB DOM",
}
MONTHS = {
    "en": "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC",
    "fr": "JANV FEVR MARS AVR MAI JUIN JUIL AOUT SEPT OCT NOV DEC",
    "es": "ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC",
    "de": "JAN FEB MAERZ APR MAI JUNI JULI AUG SEPT OKT NOV DEZ",
    "it": "GEN FEB MAR APR MAG GIU LUG AGO SET OTT NOV DIC",
    "pt": "JAN FEV MAR ABR MAI JUN JUL AGO SET OUT NOV DEZ",
}


def detect_lang():
    try:
        code = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except (AttributeError, OSError):
        return "en"
    return {0x09: "en", 0x0C: "fr", 0x0A: "es", 0x07: "de", 0x10: "it", 0x16: "pt"}.get(code, "en")


def hour_text(wall, hour12, zero):
    h = wall.hour % 12 or 12 if hour12 else wall.hour
    return f"{h:02d}" if zero else f"{h:2d}"


def template_runs(template, wall, lang, hour12=False, zero=True):
    """Expands {time} {hours} {minutes} {seconds} {day} {month} {month_name} {weekday} {year} {date}
    {ampm} into colored runs [(text, role)]."""
    lang = lang if lang in LANGS else "en"
    day = f"{wall.day:02d}" if zero else str(wall.day)
    month_name = MONTHS[lang].split()[wall.month - 1]
    date = [(f"{month_name} {wall.day}" if lang == "en" else f"{day} {month_name}", "date")]
    tokens = {
        "time": [(hour_text(wall, hour12, zero).strip(), "hours"), (":", "text"), (f"{wall.minute:02d}", "minutes")],
        "hours": [(hour_text(wall, hour12, zero).strip(), "hours")], "minutes": [(f"{wall.minute:02d}", "minutes")],
        "seconds": [(f"{wall.second:02d}", "seconds")], "day": [(day, "date")], "month": [(f"{wall.month:02d}", "date")],
        "month_name": [(month_name, "date")], "weekday": [(WEEKDAYS[lang].split()[wall.weekday()], "date")],
        "year": [(str(wall.year), "date")], "date": date, "ampm": [("AM" if wall.hour < 12 else "PM", "text")],
    }
    runs, pos = [], 0
    for m in re.finditer(r"\{(\w+)\}", template):
        if m.start() > pos:
            runs.append((template[pos:m.start()], "text"))
        runs += tokens.get(m.group(1), [(m.group(0), "text")])
        pos = m.end()
    if pos < len(template):
        runs.append((template[pos:], "text"))
    return runs


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
DISPLAY_MODES = ("time", "time_date", "scroll", "mixed", "custom")
DIGIT_ITEMS = ("hours", "minutes", "seconds", "day", "month")
TRANSITIONS = ("fade", "slide", "wipe", "dissolve", "none")
SECONDS_STYLES = ("block", "bar", "numpad", "beat", "off")
STYLES = ("solid", "gradient", "flow", "rainbow", "daytime", "digits")
BACKGROUNDS = ("off", "dim", "gradient", "breathe", "twinkle", "music")
CHIMES = ("off", "hour", "half")
WHEN = ("idle", "always", "manual")
NIGHT_ACTIONS = ("dim", "red", "off")
ROLES = ("hours", "minutes", "date", "seconds", "text")

THEMES = {
    "neon": {"style": "solid", "colors": {"hours": "#ff5900", "minutes": "#00ccff", "date": "#b36bff",
                                          "seconds": "#9a9a9a", "text": "#ffffff"},
             "background": {"mode": "off"}},
    "matrix": {"style": "solid", "colors": {"hours": "#00ff41", "minutes": "#00c832", "date": "#7dff9a",
                                            "seconds": "#0f7a2a", "text": "#00ff41"},
               "background": {"mode": "twinkle", "color": "#00ff41", "level": 45}},
    "sunset": {"style": "gradient", "gradient": ["#ff2e63", "#ff8a00", "#ffd200"],
               "colors": {"seconds": "#ff8a00"}, "background": {"mode": "dim", "color": "#ff2e63", "level": 28}},
    "ocean": {"style": "flow", "gradient": ["#00c6ff", "#0072ff", "#7f00ff"],
              "colors": {"seconds": "#00c6ff"}, "background": {"mode": "breathe", "color": "#0050ff", "level": 32}},
    "white": {"style": "solid", "colors": {"hours": "#ffffff", "minutes": "#ffffff", "date": "#ffffff",
                                           "seconds": "#808080", "text": "#ffffff"}, "background": {"mode": "off"}},
    "rainbow": {"style": "rainbow", "colors": {"seconds": "#ffffff"}, "background": {"mode": "off"}},
    "daylight": {"style": "daytime", "colors": {"seconds": "#9a9a9a"}, "background": {"mode": "off"}},
    "night_red": {"style": "solid", "colors": {"hours": "#ff1a00", "minutes": "#c81400", "date": "#ff1a00",
                                               "seconds": "#5a0800", "text": "#ff1a00"}, "background": {"mode": "off"}},
}

DEFAULTS = {
    "enabled": True,
    "lang": "",
    "show": {"when": "idle", "delay": 60, "on_lock": True, "hotkey": "Ctrl+Alt+H",
             "hide_fullscreen": True, "hide_apps": [], "off_after": 0},
    "display": {"mode": "time", "sequence": [], "secs": 2.5, "transition": "fade", "transition_secs": 0.5,
                "scroll_text": "{time} · {weekday} {date}", "scroll_speed": 5.0, "scroll_smooth": False, "hour12": False,
                "leading_zero": True, "seconds": "block", "font": "classic", "custom_font": {}},
    "look": {"theme": "neon", "style": "solid",
             "colors": {"hours": "#ff5900", "minutes": "#00ccff", "date": "#b36bff", "seconds": "#9a9a9a",
                        "text": "#ffffff"},
             "gradient": ["#ff5900", "#ff2e63", "#00ccff"], "digit_colors": ["#ff5900", "#00ccff"],
             "background": {"mode": "off", "color": "#1e2a78", "level": 25}, "chime": "hour", "brightness": 100},
    "night": {"on": False, "from": "22:00", "to": "07:00", "action": "dim", "brightness": 30},
    "keyboard": {"backend": "auto", "model": "auto"},
    "check_updates": True,
}


def _num(v, default, lo, hi):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return default
    return max(lo, min(hi, v))


def _choice(v, choices, default):
    return v if v in choices else default


def _hhmm(v, default):
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", v)
        if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
    return default


def _colors(v, default):
    v = v if isinstance(v, dict) else {}
    return {r: color_hex(hex_color(v.get(r), hex_color(default[r]))) for r in ROLES}


def _stops(v, default):
    if isinstance(v, list):
        stops = [hex_color(c) for c in v[:6]]
        if len(stops) >= 2 and all(stops):
            return [color_hex(c) for c in stops]
    return list(default)


def clean_sequence(seq):
    out = []
    for it in seq if isinstance(seq, list) else []:
        if not isinstance(it, dict):
            continue
        if it.get("show") in DIGIT_ITEMS:
            out.append({"show": it["show"], "secs": _num(it.get("secs"), 2.5, 0.5, 60)})
        elif isinstance(it.get("scroll"), str) and it["scroll"].strip():
            out.append({"scroll": it["scroll"][:200]})
        if len(out) >= 16:
            break
    return out


def clean_settings(raw):
    """User settings merged over the defaults, every value checked."""
    raw = raw if isinstance(raw, dict) else {}
    d = DEFAULTS

    def sub(name):
        v = raw.get(name)
        return v if isinstance(v, dict) else {}

    sh, di, lo, ni, kb = sub("show"), sub("display"), sub("look"), sub("night"), sub("keyboard")
    bg = lo.get("background") if isinstance(lo.get("background"), dict) else {}
    dbg = d["look"]["background"]
    hide_apps = [a.strip().lower() for a in sh.get("hide_apps", []) if isinstance(a, str) and a.strip()][:32] \
        if isinstance(sh.get("hide_apps"), list) else []
    return {
        "enabled": raw.get("enabled", True) is not False,
        "check_updates": raw.get("check_updates", True) is not False,
        "lang": _choice(raw.get("lang"), LANGS, ""),
        "show": {
            "when": _choice(sh.get("when"), WHEN, d["show"]["when"]),
            "delay": _num(sh.get("delay"), d["show"]["delay"], 5, 7200),
            "on_lock": sh.get("on_lock", True) is not False,
            "hotkey": sh["hotkey"] if isinstance(sh.get("hotkey"), str) else d["show"]["hotkey"],
            "hide_fullscreen": sh.get("hide_fullscreen", True) is not False,
            "hide_apps": hide_apps,
            "off_after": _num(sh.get("off_after"), 0, 0, 1440),
        },
        "display": {
            "mode": _choice(di.get("mode"), DISPLAY_MODES, d["display"]["mode"]),
            "sequence": clean_sequence(di.get("sequence")),
            "secs": _num(di.get("secs"), d["display"]["secs"], 0.5, 60),
            "transition": _choice(di.get("transition"), TRANSITIONS, d["display"]["transition"]),
            "transition_secs": _num(di.get("transition_secs"), d["display"]["transition_secs"], 0.1, 3),
            "scroll_text": di["scroll_text"][:200] if isinstance(di.get("scroll_text"), str) and di["scroll_text"].strip()
            else d["display"]["scroll_text"],
            "scroll_speed": _num(di.get("scroll_speed"), d["display"]["scroll_speed"], 1, 20),
            "scroll_smooth": di.get("scroll_smooth") is True,
            "hour12": di.get("hour12") is True,
            "leading_zero": di.get("leading_zero", True) is not False,
            "seconds": _choice(di.get("seconds"), SECONDS_STYLES, d["display"]["seconds"]),
            "font": _choice(di.get("font"), ("classic", "custom"), "classic"),
            "custom_font": clean_font(di.get("custom_font")),
        },
        "look": {
            "theme": lo["theme"] if isinstance(lo.get("theme"), str) else d["look"]["theme"],
            "style": _choice(lo.get("style"), STYLES, d["look"]["style"]),
            "colors": _colors(lo.get("colors"), d["look"]["colors"]),
            "gradient": _stops(lo.get("gradient"), d["look"]["gradient"]),
            "digit_colors": _stops(lo.get("digit_colors"), d["look"]["digit_colors"]),
            "background": {
                "mode": _choice(bg.get("mode"), BACKGROUNDS, dbg["mode"]),
                "color": color_hex(hex_color(bg.get("color"), hex_color(dbg["color"]))),
                "level": _num(bg.get("level"), dbg["level"], 0, 100),
            },
            "chime": _choice(lo.get("chime"), CHIMES, d["look"]["chime"]),
            "brightness": _num(lo.get("brightness"), d["look"]["brightness"], 5, 100),
        },
        "night": {
            "on": ni.get("on") is True,
            "from": _hhmm(ni.get("from"), d["night"]["from"]),
            "to": _hhmm(ni.get("to"), d["night"]["to"]),
            "action": _choice(ni.get("action"), NIGHT_ACTIONS, d["night"]["action"]),
            "brightness": _num(ni.get("brightness"), d["night"]["brightness"], 5, 100),
        },
        "keyboard": {
            "backend": _choice(kb.get("backend"), ("auto", "logitech"), "auto"),
            "model": _choice(kb.get("model"), ("auto",) + MODELS, "auto"),
        },
    }


def apply_theme(settings, name):
    """Settings with the theme's look applied (the rest kept)."""
    theme = THEMES.get(name)
    if theme is None:
        raise ValueError(f"unknown theme {name!r}")
    s = json.loads(json.dumps(settings))
    look = s["look"]
    look["theme"] = name
    for k, v in theme.items():
        if isinstance(v, dict):
            look[k] = {**look.get(k, {}), **v}
        else:
            look[k] = v
    return clean_settings(s)


def merge(base, patch):
    out = dict(base)
    for k, v in patch.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_settings(path=SETTINGS_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return clean_settings(json.load(f))
    except (OSError, ValueError):
        return clean_settings({})


def save_settings(data, path=SETTINGS_PATH):
    """Atomic write: a crash never leaves a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def minutes_of(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def night_now(night, wall):
    if not night["on"]:
        return False
    a, b, now = minutes_of(night["from"]), minutes_of(night["to"]), wall.hour * 60 + wall.minute
    return a <= now < b if a <= b else now >= a or now < b


# ---------------------------------------------------------------------------
# Rendering: background, content (digits or scrolling text), seconds, overlays, all per key
# ---------------------------------------------------------------------------
ROLE_COLOR = {"hours": "hours", "minutes": "minutes", "seconds": "seconds", "day": "date", "month": "date",
              "date": "date", "text": "text"}
SECONDS_BLOCK = ("PrtSc", "ScrLk", "Pause", "Ins", "Home", "PgUp", "Del", "End", "PgDn")
CHIME_SECS = 1.8


@functools.lru_cache(maxsize=4096)
def key_hash(key, salt=0):
    """Stable pseudo-random 0-1 per key (CRC32 is too regular on short, similar names)."""
    return int.from_bytes(hashlib.md5(f"{key}/{salt}".encode()).digest()[:4], "big") / 2 ** 32


def rasterize(model, spans, color_of):
    """Coverage of each main-block key by the spans → {key: (r, g, b, alpha)}."""
    rows = {}
    for s in spans:
        rows.setdefault(s[0], []).append(s)
    out = {}
    for key, x0, x1, row, cx in model.grid:
        lst = rows.get(row)
        if not lst:
            continue
        width = x1 - x0
        acc = cr = cg = cb = 0.0
        for _, s0, s1, role, n in lst:
            ov = min(x1, s1) - max(x0, s0)
            if ov > 0:
                w = ov / width
                c = color_of(role, n, cx)
                acc += w
                cr += c[0] * w
                cg += c[1] * w
                cb += c[2] * w
        if acc > 0.001:
            a = min(1.0, acc)
            prev = out.get(key)
            if prev is None or a > prev[3]:
                out[key] = (cr / acc, cg / acc, cb / acc, a)
    return out


def digit_spans(model, text, role, custom=None):
    spans = []
    for pos, ch in enumerate(text[:2]):
        for k in font_keys(model, ch, pos, custom):
            for kk, x, y, w, h in model.rects:
                if kk == k and y in ROW_YS[:5]:
                    spans.append((ROW_YS.index(y), x, x + w, role, pos))
    return spans


class Renderer:
    """Turns settings and the time into one color per key. Pure: no device, no clock of its own."""

    def __init__(self, model, settings, lang="en"):
        self.model = model
        self.lang = lang
        self.configure(settings)

    def configure(self, settings):
        self.s = settings
        d = settings["display"]
        self.items = self._sequence(d)
        self.trans = d["transition"]
        self.tsecs = 0.0 if self.trans == "none" else d["transition_secs"]
        self.speed = d["scroll_speed"]
        self.custom_font = d["custom_font"] if d["font"] == "custom" else None
        lo = settings["look"]
        self.colors = {r: hex_color(c) for r, c in lo["colors"].items()}
        self.gradient = [hex_color(c) for c in lo["gradient"]]
        self.digit_colors = [hex_color(c) for c in lo["digit_colors"]]

    @staticmethod
    def _sequence(d):
        secs = d["secs"]
        if d["mode"] == "custom" and d["sequence"]:
            return [dict(it) if "scroll" in it else {"show": it["show"], "secs": it["secs"]} for it in d["sequence"]]
        if d["mode"] == "time_date":
            return [{"show": w, "secs": secs} for w in ("hours", "minutes", "day", "month")]
        if d["mode"] == "scroll":
            return [{"scroll": d["scroll_text"]}]
        if d["mode"] == "mixed":
            return [{"show": w, "secs": secs} for w in ("hours", "minutes", "hours", "minutes")] + \
                   [{"scroll": "{weekday} {date}"}]
        return [{"show": "hours", "secs": secs}, {"show": "minutes", "secs": secs}]

    # -- content --------------------------------------------------------------
    def _digits(self, what, wall):
        d = self.s["display"]
        if what == "hours":
            return hour_text(wall, d["hour12"], d["leading_zero"])
        value = {"minutes": wall.minute, "seconds": wall.second, "day": wall.day, "month": wall.month}[what]
        return f"{value:02d}" if what in ("minutes", "seconds") or d["leading_zero"] else f"{value:2d}"

    def _columns(self, item, wall):
        d = self.s["display"]
        return text_columns(template_runs(item["scroll"], wall, self.lang, d["hour12"], d["leading_zero"]))

    def _duration(self, item, wall):
        if "scroll" in item:
            return (MAIN_W + len(self._columns(item, wall))) / self.speed
        return item["secs"] + 2 * self.tsecs

    def content(self, t, wall):
        """(spans, fade 0-1, mask or None) shown `t` seconds after the clock appeared."""
        durations = [max(0.1, self._duration(it, wall)) for it in self.items]
        u = t % sum(durations)
        for item, dur in zip(self.items, durations):
            if u < dur:
                break
            u -= dur
        if "scroll" in item:
            cols, offset = self._columns(item, wall), MAIN_W - self.speed * u
            if self.s["display"]["scroll_smooth"]:
                return scroll_spans(cols, offset), 1.0, None
            return ("crisp", cols, math.floor(offset)), 1.0, None
        spans = digit_spans(self.model, self._digits(item["show"], wall), item["show"], self.custom_font)
        T = self.tsecs
        if T <= 0:
            return spans, 1.0, None
        if u < T:
            p, entering = u / T, True
        elif u > dur - T:
            p, entering = max(0.0, (dur - u) / T), False
        else:
            return spans, 1.0, None
        if self.trans == "fade":
            return spans, p, None
        if self.trans == "slide":
            dx = (1 - p) * (MAIN_W + 2) * (1 if entering else -1)
            return [(r, x0 + dx, x1 + dx, role, n) for r, x0, x1, role, n in spans], 1.0, None
        if self.trans == "wipe":
            edge = p * (MAIN_W + 2) - 1 if entering else (1 - p) * (MAIN_W + 2) - 1
            if entering:
                return spans, 1.0, lambda key, cx: min(1.0, max(0.0, edge - cx + 0.5))
            return spans, 1.0, lambda key, cx: min(1.0, max(0.0, cx - edge + 0.5))
        return spans, 1.0, lambda key, cx: 1.0 if key_hash(key) < p else 0.0     # dissolve

    def color_fn(self, t, wall, night_red):
        if night_red:
            red = (255.0, 20.0, 0.0)
            return lambda role, n, x: red
        style, colors = self.s["look"]["style"], self.colors
        if style == "gradient":
            return lambda role, n, x: gradient_at(self.gradient, x / MAIN_W)
        if style == "flow":
            loop = self.gradient + [self.gradient[0]]
            return lambda role, n, x: gradient_at(loop, (x / MAIN_W * 0.5 + t / 8) % 1.0)
        if style == "rainbow":
            return lambda role, n, x: hsv(x / MAIN_W * 0.8 + t / 10)
        if style == "daytime":
            c = daytime_color(wall)
            return lambda role, n, x: c
        if style == "digits":
            dc = self.digit_colors
            return lambda role, n, x: dc[n % len(dc)]
        return lambda role, n, x: colors[ROLE_COLOR.get(role, "text")]

    # -- layers ---------------------------------------------------------------
    def background(self, t, night_red):
        bg = self.s["look"]["background"]
        mode = bg["mode"]
        if mode in ("off", "music") or night_red:
            return {}
        color, level = hex_color(bg["color"]), bg["level"] / 100
        m = self.model
        out = {}
        if mode == "dim":
            f = perceived(level)
            c = tuple(v * f for v in color)
            return {k: c for k in m.keys}
        if mode == "gradient":
            f = perceived(level)
            return {k: tuple(v * f for v in gradient_at(self.gradient, m.center[k][0] / m.width)) for k in m.keys}
        if mode == "breathe":
            f = perceived(level * (0.3 + 0.7 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 5))))
            c = tuple(v * f for v in color)
            return {k: c for k in m.keys}
        for k in m.keys:                                        # twinkle
            period = 2.5 + 4 * key_hash(k, 1)
            v = max(0.0, math.sin(2 * math.pi * (t / period + key_hash(k, 2)))) ** 8
            f = perceived(level * v)
            if f > 0.0005:
                out[k] = tuple(c * f for c in color)
        return out

    def seconds(self, wall, night_red):
        style = self.s["display"]["seconds"]
        color = (255.0, 20.0, 0.0) if night_red else hex_color(self.s["look"]["colors"]["seconds"])
        m = self.model
        sec = wall.second + wall.microsecond / 1e6
        if style == "numpad" and not m.has_numpad:
            style = "block"
        out = {}
        if style == "block":
            progress = sec / (60 / len(SECONDS_BLOCK))
            for i, k in enumerate(SECONDS_BLOCK):
                level = min(1.0, max(0.0, progress - i))
                if level > 0:
                    out[k] = (*color, perceived(level))
        elif style == "bar":
            length = sec / 60 * MAIN_W
            for k, x, y, w, h in m.rects:
                if y == ROW_YS[5] and x < MAIN_W:
                    level = min(1.0, max(0.0, (length - x) / w))
                    if level > 0:
                        out[k] = (*color, perceived(level))
        elif style == "numpad":
            tens, units = f"KP{wall.second // 10}", f"KP{wall.second % 10}"
            out[tens] = (*color, 1.0)
            out[units] = (*hex_color(self.s["look"]["colors"]["minutes"]), 1.0) if tens != units else (*color, 1.0)
        elif style == "beat":
            out["Pause"] = (*color, perceived(max(0.0, 1 - (sec % 1) * 2.5)))
        return out

    def chime(self, u):
        m = self.model
        p = -3 + (m.width + 6) * u / CHIME_SECS
        out = {}
        for k in m.keys:
            x = m.center[k][0]
            a = math.exp(-((x - p) / 1.6) ** 2)
            if a > 0.01:
                out[k] = (*hsv(x / m.width * 0.8 + u / 3), a)
        return out

    def frame(self, t, wall, chime_u=None, night=False, dark=False):
        """{key: (r, g, b)} 0-255 for every key of the model."""
        m = self.model
        if dark:
            return {k: (0, 0, 0) for k in m.keys}
        ns = self.s["night"]
        night_red = night and ns["action"] == "red"
        bright = self.s["look"]["brightness"] / 100
        if night and ns["action"] in ("dim", "red"):
            bright *= ns["brightness"] / 100
        gain = perceived(bright)
        bg = self.background(t, night_red)
        if chime_u is not None:
            content = {}
            overlay = self.chime(chime_u)
        else:
            spans, fade, mask = self.content(t, wall)
            color_of = self.color_fn(t, wall, night_red)
            if isinstance(spans, tuple):                  # ("crisp", columns, whole-key offset)
                content = scroll_crisp(m, spans[1], spans[2], color_of)
            else:
                content = rasterize(m, spans, color_of)
            if fade < 1 or mask is not None:
                f = perceived(fade)
                content = {k: (r, g, b, a * f * (mask(k, m.center[k][0]) if mask else 1.0))
                           for k, (r, g, b, a) in content.items()}
            overlay = {}
        secs = self.seconds(wall, night_red)
        out = {}
        for k in m.keys:
            c = bg.get(k, BLACK)
            for layer in (content, secs, overlay):
                v = layer.get(k)
                if v is not None and v[3] > 0:
                    a = v[3]
                    c = (c[0] + (v[0] - c[0]) * a, c[1] + (v[1] - c[1]) * a, c[2] + (v[2] - c[2]) * a)
            out[k] = tuple(max(0, min(255, int(round(x * gain)))) for x in c)
        return out


# ---------------------------------------------------------------------------
# Windows: idle time, lock state, full-screen apps, running processes, hotkey
# ---------------------------------------------------------------------------
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def session_locked():
    """True while the lock screen (or another secure desktop) is up."""
    u = ctypes.windll.user32
    u.OpenInputDesktop.restype = wintypes.HANDLE
    h = u.OpenInputDesktop(0, False, 0x0100)          # DESKTOP_SWITCHDESKTOP
    if not h:
        return True
    try:
        return not u.SwitchDesktop(wintypes.HANDLE(h))
    finally:
        u.CloseDesktop(wintypes.HANDLE(h))


def fullscreen_app():
    """A game or video runs full screen, or presentation mode is on (SHQueryUserNotificationState)."""
    state = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
    except (AttributeError, OSError):
        return False
    return state.value in (2, 3, 4)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def running_exes():
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(2, 0)                 # TH32CS_SNAPPROCESS
    names = set()
    if not snap or snap == wintypes.HANDLE(-1).value:
        return names
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(wintypes.HANDLE(snap), ctypes.byref(e))
        while ok:
            names.add(e.szExeFile.lower())
            ok = k32.Process32NextW(wintypes.HANDLE(snap), ctypes.byref(e))
    finally:
        k32.CloseHandle(wintypes.HANDLE(snap))
    return names


MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}


def parse_hotkey(text):
    """'Ctrl+Alt+H' → (modifiers, virtual key) or None."""
    if not isinstance(text, str) or not text.strip():
        return None
    mods, vk = 0, None
    for part in text.replace(" ", "").split("+"):
        p = part.lower()
        if p in MODS:
            mods |= MODS[p]
        elif len(p) == 1 and p.isalnum():
            vk = ord(p.upper())
        elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", p):
            vk = 0x6F + int(p[1:])
        else:
            return None
    return (mods, vk) if vk and mods else None


class Hotkey(threading.Thread):
    """Calls `on_press` when the global hotkey is pressed (its own thread and message queue)."""

    def __init__(self, combo, on_press):
        super().__init__(name="keyboard-clock-hotkey", daemon=True)
        self.combo, self.on_press, self.tid, self.ok = combo, on_press, None, False

    def run(self):
        u = ctypes.windll.user32
        self.tid = ctypes.windll.kernel32.GetCurrentThreadId()
        mods, vk = self.combo
        self.ok = bool(u.RegisterHotKey(None, 1, mods | 0x4000, vk))       # MOD_NOREPEAT
        if not self.ok:
            log("The hotkey is already used by another app.")
            return
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:                                     # WM_HOTKEY
                self.on_press()
        u.UnregisterHotKey(None, 1)

    def stop(self):
        if self.tid:
            ctypes.windll.user32.PostThreadMessageW(self.tid, 0x0012, 0, 0)   # WM_QUIT


# ---------------------------------------------------------------------------
# Logitech G HUB back-end (LED SDK shipped with G HUB)
# ---------------------------------------------------------------------------
class Unsupported(OSError):
    pass


class LogitechBackend:
    name = "Logitech G HUB"

    def __init__(self):
        bits = "x64" if struct.calcsize("P") == 8 else "x86"
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [os.path.join(here, f"sdk_legacy_led_{bits}.dll"),
                      rf"C:\Program Files\LGHUB\sdks\sdk_legacy_led_{bits}.dll",
                      rf"C:\Program Files\LGHUB\sdk_legacy_led_{bits}.dll"]
        path = next((c for c in candidates if os.path.isfile(c)), None)
        if path is None:
            raise Unsupported("Logitech G HUB's LED SDK was not found. Is G HUB installed?")
        d = self.dll = ctypes.CDLL(path)
        d.LogiLedInitWithName.argtypes = [ctypes.c_char_p]
        d.LogiLedInitWithName.restype = ctypes.c_bool
        d.LogiLedSetTargetDevice.argtypes = [ctypes.c_int]
        d.LogiLedSetTargetDevice.restype = ctypes.c_bool
        d.LogiLedSetLighting.argtypes = [ctypes.c_int] * 3
        d.LogiLedSetLighting.restype = ctypes.c_bool
        d.LogiLedSetLightingForKeyWithKeyName.argtypes = [ctypes.c_int] * 4
        d.LogiLedSetLightingForKeyWithKeyName.restype = ctypes.c_bool
        d.LogiLedShutdown.argtypes = []
        d.LogiLedShutdown.restype = None
        self.sent = {}
        self.full_at = 0.0

    def open(self):
        """Takes over the lighting (the keyboard goes dark). False if G HUB doesn't answer."""
        if not self.dll.LogiLedInitWithName(APP.encode()):
            return False
        time.sleep(0.5)                       # let G HUB finish the connection
        self.dll.LogiLedSetTargetDevice(4)    # LOGI_DEVICETYPE_PERKEY_RGB
        self.dll.LogiLedSetLighting(0, 0, 0)
        self.sent.clear()
        self.full_at = time.monotonic()
        return True

    def send(self, frame):
        if time.monotonic() - self.full_at > 30:      # resend everything now and then
            self.sent.clear()
            self.full_at = time.monotonic()
        for key, (r, g, b) in frame.items():
            code = LOGITECH_LOGO if key == "Logo" else KEY_CODES[key][1]
            pct = (round(r / 2.55), round(g / 2.55), round(b / 2.55))
            if self.sent.get(code) != pct:
                self.dll.LogiLedSetLightingForKeyWithKeyName(code, *pct)
                self.sent[code] = pct

    def release(self):
        """G HUB takes the lighting back (the active profile's effect)."""
        self.dll.LogiLedShutdown()


def open_backend(settings):
    return LogitechBackend()


# ---------------------------------------------------------------------------
# The clock: decides when to show, renders and sends frames
# ---------------------------------------------------------------------------
FPS = 25


class StopSignal:
    """Named event: single instance lock and quit signal (--stop sets it)."""

    def __init__(self):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateEventW.restype = wintypes.HANDLE
        k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.k32 = k32
        self.h = k32.CreateEventW(None, True, False, STOP_EVENT)
        self.already_running = ctypes.get_last_error() == 183

    def wait(self, seconds):
        return self.k32.WaitForSingleObject(self.h, max(0, int(seconds * 1000))) == 0

    def set(self):
        ctypes.windll.kernel32.SetEvent(wintypes.HANDLE(self.h))

    def is_set(self):
        return self.wait(0)


def request_stop():
    k32 = ctypes.windll.kernel32
    k32.OpenEventW.restype = wintypes.HANDLE
    h = k32.OpenEventW(0x0002, False, STOP_EVENT)
    if not h:
        return False
    k32.SetEvent(wintypes.HANDLE(h))
    k32.CloseHandle(wintypes.HANDLE(h))
    return True


class Clock:
    """Watches idle time, lock, hotkey, full-screen apps and night hours, and drives the keyboard.
    The app changes its settings with apply() and is told about status changes through notify()."""

    def __init__(self, stop, overrides=None, settings_path=SETTINGS_PATH):
        self.stop, self.path, self.overrides = stop, settings_path, overrides or {}
        self.settings = self._load()
        self.mtime = self._mtime()
        self.version = 0
        self.manual = False              # shown with the hotkey
        self.paused_until = 0.0          # time.monotonic()
        self.override = None             # (until, frame function or None, start): show now, font editor, test
        self.status = "waiting"
        self.last_frame = {}
        self.notify = lambda: None
        self.new_version = self.update_page = self.update_info = None
        self.lang = self.settings["lang"] or detect_lang()

    def _mtime(self):
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return 0.0

    def _load(self):
        s = load_settings(self.path)
        return clean_settings(merge(s, self.overrides)) if self.overrides else s

    @property
    def check_updates(self):
        return self.settings["check_updates"]

    def apply(self, settings):
        """New settings (already saved, or live while a slider moves)."""
        self.settings = settings
        self.mtime = self._mtime()
        self.version += 1

    def model_name(self, s=None):
        s = s or self.settings
        return s["keyboard"]["model"] if s["keyboard"]["model"] != "auto" else default_model()

    def toggle(self):
        self.manual = not self.manual
        self.notify()

    def show_for(self, seconds, frame_fn=None):
        """Shows the clock (or frame_fn(t)) on the keyboard for a few seconds, whatever the triggers say."""
        now = time.monotonic()
        start = self.override[2] if self.override and self.override[1] is frame_fn else now
        self.override = (now + seconds, frame_fn, start)
        log(f"Show on the keyboard for {seconds:g} s requested.")

    def pause(self, seconds):
        self.paused_until = time.monotonic() + seconds if seconds else 0.0
        self.notify()

    def paused(self):
        return time.monotonic() < self.paused_until

    def _set_status(self, status):
        if status != self.status:
            self.status = status
            self.notify()

    def run(self):
        backend, renderer, model_name = None, None, None
        holding, shown_at, next_try, last_check = False, 0.0, 0.0, -9.0
        locked = full = apps_hit = False
        chime_at = chimed = None
        hotkey, hotkey_text, seen = None, None, None
        try:
            while True:
                now = time.monotonic()
                if now - last_check >= 1.0:                       # slower checks, once a second
                    last_check = now
                    if self._mtime() != self.mtime:              # edited by hand or by another process
                        self.apply(self._load())
                        log("Settings reloaded.")
                    sh = self.settings["show"]
                    locked = sh["on_lock"] and session_locked()
                    full = sh["hide_fullscreen"] and fullscreen_app()
                    apps_hit = bool(sh["hide_apps"]) and bool(running_exes() & set(sh["hide_apps"]))
                s = self.settings
                if self.version != seen:
                    seen = self.version
                    self.lang = s["lang"] or detect_lang()
                    name = self.model_name(s)
                    if renderer is None or name != model_name:
                        model_name, renderer = name, Renderer(Model(name), s, self.lang)
                    else:
                        renderer.configure(s)
                        renderer.lang = self.lang
                    if s["show"]["hotkey"] != hotkey_text:
                        if hotkey:
                            hotkey.stop()
                        hotkey_text, combo = s["show"]["hotkey"], parse_hotkey(s["show"]["hotkey"])
                        hotkey = Hotkey(combo, self.toggle) if combo else None
                        if hotkey:
                            hotkey.start()
                sh = s["show"]
                ov = self.override
                if ov and now >= ov[0]:
                    self.override = ov = None
                idle = idle_seconds()
                wanted = s["enabled"] and not self.paused() and (
                    self.manual or sh["when"] == "always" or (sh["when"] == "idle" and idle >= sh["delay"]) or locked)
                hidden = wanted and not locked and not self.manual and (full or apps_hit)
                want = bool(ov) or (wanted and not hidden)
                if want and not holding and now >= next_try:
                    try:
                        backend = backend or open_backend(s)
                        holding = backend.open()
                    except (Unsupported, OSError) as e:
                        log(f"Keyboard not available: {e}")
                        holding = False
                    if holding:
                        shown_at, chime_at = now, None
                        log("Showing on the keyboard" + (" (on demand)" if ov else ""))
                    else:
                        log("G HUB did not hand over the lighting; trying again in a few seconds.")
                        next_try = now + (2 if ov else 10)
                elif not want and holding:
                    backend.release()
                    holding = False
                    log("Lighting handed back to G HUB.")
                if holding:
                    status = "showing"
                elif want:
                    status = "no_keyboard"
                elif not s["enabled"]:
                    status = "off"
                elif self.paused():
                    status = "paused"
                elif hidden:
                    status = "hidden_app"
                else:
                    status = "waiting"
                self._set_status(status)
                if holding:
                    wall = dt.datetime.now()
                    if ov and ov[1]:
                        frame = ov[1](now - ov[2])
                    else:
                        chime = s["look"]["chime"]
                        if chime != "off" and wall.second < 2 and (wall.minute == 0 or (chime == "half" and wall.minute == 30)):
                            stamp = (wall.hour, wall.minute)
                            if stamp != chimed and now - shown_at > 2:
                                chimed, chime_at = stamp, now
                        chime_u = None
                        if chime_at is not None:
                            chime_u = now - chime_at
                            if chime_u >= CHIME_SECS:
                                chime_at, chime_u, shown_at = None, None, now     # back to the hours
                        night = night_now(s["night"], wall)
                        dark = not ov and ((night and s["night"]["action"] == "off") or (
                            sh["off_after"] > 0 and not self.manual and now - shown_at > sh["off_after"] * 60))
                        frame = renderer.frame(now - shown_at, wall, chime_u, night, dark)
                    self.last_frame = frame
                    try:
                        backend.send(frame)
                    except OSError as e:
                        log(f"Lost the keyboard: {e}")
                        holding = False
                        next_try = now + 5
                if self.stop.wait(1 / FPS if holding else 0.2):
                    return
        finally:
            if holding:
                backend.release()
            if hotkey:
                hotkey.stop()


# ---------------------------------------------------------------------------
# Demo scenes (shown on the keyboard with --demo, drawn into a picture with --preview)
# ---------------------------------------------------------------------------
DEMO = [
    ("Hours then minutes, fade", 7, {"look": {"theme": "neon"}}),
    ("Time and date, slide", 13, {"display": {"mode": "time_date", "transition": "slide", "transition_secs": 0.6}}),
    ("Scrolling text, rainbow", 14, {"display": {"mode": "scroll", "scroll_text": "{time} · {weekday} {date}"},
                                      "look": {"theme": "rainbow"}}),
    ("Wipe, twinkling stars", 7, {"display": {"transition": "wipe", "transition_secs": 0.6}, "look": {"theme": "matrix"}}),
    ("Flowing gradient, breathing background", 7, {"look": {"theme": "ocean"}}),
    ("Sunset gradient, dissolve", 7, {"display": {"transition": "dissolve", "transition_secs": 0.7},
                                       "look": {"theme": "sunset"}}),
    ("Colors of the day, seconds bar", 7, {"display": {"seconds": "bar"}, "look": {"theme": "daylight"}}),
    ("Hourly chime", 4, {"chime": True}),
    ("Night, red", 7, {"night": {"on": True, "from": "00:00", "to": "23:59", "action": "red", "brightness": 40}}),
]


def demo_settings(base, patch):
    patch = {k: v for k, v in patch.items() if k != "chime"}
    theme = patch.get("look", {}).get("theme")
    s = apply_theme(base, theme) if theme else base
    return clean_settings(merge(s, patch))


def run_demo(stop, base, lang):
    backend = open_backend(base)
    if not backend.open():
        log("G HUB did not answer. Is it running, with “Allow games & applications to control my lighting” on?")
        return 1
    model = Model(base["keyboard"]["model"] if base["keyboard"]["model"] != "auto" else default_model())
    try:
        for name, secs, patch in DEMO:
            log(f"  demo: {name}")
            s = demo_settings(base, patch)
            r = Renderer(model, s, lang)
            start = time.monotonic()
            while (t := time.monotonic() - start) < secs:
                wall = dt.datetime.now()
                chime_u = t % CHIME_SECS if patch.get("chime") else None
                backend.send(r.frame(t, wall, chime_u, night_now(s["night"], wall)))
                if stop.wait(1 / FPS):
                    return 0
    finally:
        backend.release()
    return 0


def run_bench():
    backend = open_backend(load_settings())
    if not backend.open():
        log("G HUB did not answer.")
        return 1
    try:
        keys = [KEY_CODES[k][1] for k in "QWERTYUIOPASDFGHJKLZXCVBNM"]
        n = 0
        start = time.perf_counter()
        for i in range(12):
            for code in keys:
                backend.dll.LogiLedSetLightingForKeyWithKeyName(code, (i % 2) * 60, 20, 60 - (i % 2) * 60)
                n += 1
        per = (time.perf_counter() - start) / n * 1000
        log(f"{per:.3f} ms per key → about {int(1000 / per)} keys per second")
    finally:
        backend.release()
    return 0


# ---------------------------------------------------------------------------
# Pictures of the keyboard (no dependency: a tiny PNG writer)
# ---------------------------------------------------------------------------
class Canvas:
    def __init__(self, w, h, color=(18, 18, 22)):
        self.w, self.h = w, h
        self.px = bytearray(bytes(color) * (w * h))

    def rect(self, x0, y0, x1, y1, color):
        x0, x1 = max(0, int(x0)), min(self.w, int(x1))
        c = bytes(int(max(0, min(255, v))) for v in color)
        for y in range(max(0, int(y0)), min(self.h, int(y1))):
            self.px[(y * self.w + x0) * 3:(y * self.w + x1) * 3] = c * max(0, x1 - x0)

    def text(self, x, y, text, scale=2, color=(150, 156, 170)):
        for bits, _, _ in text_columns([(text, "text")]):
            for r in range(5):
                if bits[r]:
                    self.rect(x, y + r * scale, x + scale, y + (r + 1) * scale, color)
            x += scale

    def save(self, path):
        raw = b"".join(b"\x00" + bytes(self.px[y * self.w * 3:(y + 1) * self.w * 3]) for y in range(self.h))

        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


KEYCAP = (46, 48, 56)


def draw_keyboard(canvas, model, frame, ox, oy, scale):
    for k, x, y, w, h in model.rects:
        c = frame.get(k, (0, 0, 0))
        color = tuple(KEYCAP[i] + c[i] * (255 - KEYCAP[i]) / 255 for i in range(3))   # LED light on a dark keycap
        canvas.rect(ox + (x + 0.06) * scale, oy + (y + 0.06) * scale,
                    ox + (x + w - 0.06) * scale, oy + (y + h - 0.06) * scale, color)


def save_preview(path, scenes, model_name="tkl-iso", scale=26):
    """scenes: [(label, settings, t, wall, chime_u)] → one keyboard per scene, stacked."""
    model = Model(model_name)
    kw, kh = int(model.width * scale) + 20, int(model.height * scale) + 34
    canvas = Canvas(kw, kh * len(scenes) + 6)
    for i, (label, s, t, wall, chime_u) in enumerate(scenes):
        frame = Renderer(model, s, "en").frame(t, wall, chime_u, night_now(s["night"], wall))
        canvas.text(10, i * kh + 8, label)
        draw_keyboard(canvas, model, frame, 10, i * kh + 26, scale)
    canvas.save(path)


def preview_scenes(base, wall):
    scenes = []
    for name, secs, patch in DEMO:
        s = demo_settings(base, patch)
        if patch.get("chime"):
            scenes.append((name, s, 1.0, wall, 0.9))
            continue
        r = Renderer(Model("tkl-iso"), s, "en")
        if s["display"]["mode"] == "scroll":
            times = (3.5,)
        else:
            T = r.tsecs
            times = (T + 1.0, r.items[0]["secs"] + T * 1.5)     # held, then mid-transition
        for t in times:
            scenes.append((f"{name} t={t:g}", s, t, wall, None))
    return scenes


# =============================================================================
# The app: icon next to the clock with its panel, the window (pages, live keyboard, font editor), installing,
# starting with Windows, updates. The window toolkit comes from Glowback (same author, MIT).
# =============================================================================
wt = wintypes
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdiplus = ctypes.WinDLL("gdiplus")
dwmapi = ctypes.WinDLL("dwmapi")
HANDLE = VP = ctypes.c_void_p
PVP = ctypes.POINTER(ctypes.c_void_p)
F = ctypes.c_float
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
byref, sizeof = ctypes.byref, ctypes.sizeof


class GUID(ctypes.Structure):
    _fields_ = [("a", wt.DWORD), ("b", wt.WORD), ("c", wt.WORD), ("d", ctypes.c_ubyte * 8)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD), ("szDevice", wt.WCHAR * 32)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", HANDLE), ("hIcon", HANDLE), ("hCursor", HANDLE),
                ("hbrBackground", HANDLE), ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
                ("hIconSm", HANDLE)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", HANDLE), ("uID", wt.UINT), ("uFlags", wt.UINT),
                ("uCallbackMessage", wt.UINT), ("hIcon", HANDLE), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", HANDLE)]


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", HANDLE), ("uCallbackMessage", wt.UINT), ("uEdge", wt.UINT),
                ("rc", wt.RECT), ("lParam", wt.LPARAM)]


class MEASUREITEMSTRUCT(ctypes.Structure):
    _fields_ = [("CtlType", wt.UINT), ("CtlID", wt.UINT), ("itemID", wt.UINT), ("itemWidth", wt.UINT),
                ("itemHeight", wt.UINT), ("itemData", ctypes.c_size_t)]


class DRAWITEMSTRUCT(ctypes.Structure):
    _fields_ = [("CtlType", wt.UINT), ("CtlID", wt.UINT), ("itemID", wt.UINT), ("itemAction", wt.UINT),
                ("itemState", wt.UINT), ("hwndItem", HANDLE), ("hDC", HANDLE), ("rcItem", wt.RECT),
                ("itemData", ctypes.c_size_t)]


class MENUINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("fMask", wt.DWORD), ("dwStyle", wt.DWORD), ("cyMax", wt.UINT),
                ("hbrBack", HANDLE), ("dwContextHelpID", wt.DWORD), ("dwMenuData", ctypes.c_size_t)]


class MENUITEMINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("fMask", wt.UINT), ("fType", wt.UINT), ("fState", wt.UINT), ("wID", wt.UINT),
                ("hSubMenu", HANDLE), ("hbmpChecked", HANDLE), ("hbmpUnchecked", HANDLE),
                ("dwItemData", ctypes.c_size_t), ("dwTypeData", wt.LPWSTR), ("cch", wt.UINT), ("hbmpItem", HANDLE)]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", wt.BOOL), ("SuppressExternalCodecs", wt.BOOL)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", HANDLE), ("fErase", wt.BOOL), ("rcPaint", wt.RECT), ("fRestore", wt.BOOL),
                ("fIncUpdate", wt.BOOL), ("rgbReserved", ctypes.c_ubyte * 32)]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwFlags", wt.DWORD), ("hwndTrack", HANDLE), ("dwHoverTime", wt.DWORD)]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", wt.POINT), ("ptMaxSize", wt.POINT), ("ptMaxPosition", wt.POINT),
                ("ptMinTrackSize", wt.POINT), ("ptMaxTrackSize", wt.POINT)]


class POINTF(ctypes.Structure):
    _fields_ = [("X", F), ("Y", F)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def _sig(fn, res, *args):
    fn.restype = res
    fn.argtypes = list(args)


_sig(user32.RegisterClassExW, wt.WORD, ctypes.POINTER(WNDCLASSEXW))
_sig(user32.CreateWindowExW, HANDLE, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
     ctypes.c_int, ctypes.c_int, HANDLE, HANDLE, HANDLE, ctypes.c_void_p)
_sig(user32.DefWindowProcW, LRESULT, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
_sig(user32.GetMessageW, wt.BOOL, ctypes.POINTER(wt.MSG), HANDLE, wt.UINT, wt.UINT)
_sig(user32.TranslateMessage, wt.BOOL, ctypes.POINTER(wt.MSG))
_sig(user32.DispatchMessageW, LRESULT, ctypes.POINTER(wt.MSG))
_sig(user32.IsDialogMessageW, wt.BOOL, HANDLE, ctypes.POINTER(wt.MSG))
_sig(user32.PostMessageW, wt.BOOL, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
_sig(user32.SendMessageW, LRESULT, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
_sig(user32.PostQuitMessage, None, ctypes.c_int)
_sig(user32.DestroyWindow, wt.BOOL, HANDLE)
_sig(user32.CreatePopupMenu, HANDLE)
_sig(user32.AppendMenuW, wt.BOOL, HANDLE, wt.UINT, ctypes.c_size_t, ctypes.c_void_p)
_sig(user32.InsertMenuItemW, wt.BOOL, HANDLE, wt.UINT, wt.BOOL, ctypes.POINTER(MENUITEMINFOW))
_sig(user32.TrackPopupMenu, ctypes.c_int, HANDLE, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, HANDLE,
     ctypes.c_void_p)
_sig(user32.DestroyMenu, wt.BOOL, HANDLE)
_sig(user32.SetMenuInfo, wt.BOOL, HANDLE, ctypes.POINTER(MENUINFO))
_sig(user32.GetCursorPos, wt.BOOL, ctypes.POINTER(wt.POINT))
_sig(user32.SetForegroundWindow, wt.BOOL, HANDLE)
_sig(user32.RegisterWindowMessageW, wt.UINT, wt.LPCWSTR)
_sig(user32.LoadImageW, HANDLE, HANDLE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT)
_sig(user32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
_sig(user32.DestroyIcon, wt.BOOL, HANDLE)
_sig(user32.MonitorFromRect, HANDLE, ctypes.POINTER(wt.RECT), wt.DWORD)
_sig(user32.MonitorFromPoint, HANDLE, wt.POINT, wt.DWORD)
_sig(user32.GetMonitorInfoW, wt.BOOL, HANDLE, ctypes.POINTER(MONITORINFOEXW))
_sig(user32.LoadCursorW, HANDLE, HANDLE, ctypes.c_void_p)
_sig(user32.GetClientRect, wt.BOOL, HANDLE, ctypes.POINTER(wt.RECT))
_sig(user32.GetWindowRect, wt.BOOL, HANDLE, ctypes.POINTER(wt.RECT))
_sig(user32.MessageBoxW, ctypes.c_int, HANDLE, wt.LPCWSTR, wt.LPCWSTR, wt.UINT)
_sig(user32.FillRect, ctypes.c_int, HANDLE, ctypes.POINTER(wt.RECT), HANDLE)
_sig(user32.DrawTextW, ctypes.c_int, HANDLE, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT)
_sig(user32.DrawIconEx, wt.BOOL, HANDLE, ctypes.c_int, ctypes.c_int, HANDLE, ctypes.c_int, ctypes.c_int, wt.UINT,
     HANDLE, wt.UINT)
_sig(user32.BeginPaint, HANDLE, HANDLE, ctypes.POINTER(PAINTSTRUCT))
_sig(user32.EndPaint, wt.BOOL, HANDLE, ctypes.POINTER(PAINTSTRUCT))
_sig(user32.InvalidateRect, wt.BOOL, HANDLE, ctypes.c_void_p, wt.BOOL)
_sig(user32.ShowWindow, wt.BOOL, HANDLE, ctypes.c_int)
_sig(user32.IsWindow, wt.BOOL, HANDLE)
_sig(user32.IsIconic, wt.BOOL, HANDLE)
_sig(user32.EnableWindow, wt.BOOL, HANDLE, wt.BOOL)
_sig(user32.SetFocus, HANDLE, HANDLE)
_sig(user32.GetWindowTextW, ctypes.c_int, HANDLE, wt.LPWSTR, ctypes.c_int)
_sig(user32.GetWindowTextLengthW, ctypes.c_int, HANDLE)
_sig(user32.TrackMouseEvent, wt.BOOL, ctypes.POINTER(TRACKMOUSEEVENT))
_sig(user32.SetTimer, ctypes.c_size_t, HANDLE, ctypes.c_size_t, wt.UINT, ctypes.c_void_p)
_sig(user32.KillTimer, wt.BOOL, HANDLE, ctypes.c_size_t)
_sig(user32.SetWindowPos, wt.BOOL, HANDLE, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT)
_sig(user32.SetCapture, HANDLE, HANDLE)
_sig(user32.ReleaseCapture, wt.BOOL)
_sig(user32.GetKeyState, ctypes.c_short, ctypes.c_int)
_sig(user32.FindWindowW, HANDLE, wt.LPCWSTR, wt.LPCWSTR)
_sig(user32.ClientToScreen, wt.BOOL, HANDLE, ctypes.POINTER(wt.POINT))
_sig(user32.AllowSetForegroundWindow, wt.BOOL, wt.DWORD)
_sig(user32.GetWindowThreadProcessId, wt.DWORD, HANDLE, ctypes.POINTER(wt.DWORD))
_sig(shell32.Shell_NotifyIconW, wt.BOOL, wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
_sig(shell32.SHAppBarMessage, ctypes.c_size_t, wt.DWORD, ctypes.POINTER(APPBARDATA))
_sig(k32.GetModuleHandleW, HANDLE, wt.LPCWSTR)
_sig(k32.SetEvent, wt.BOOL, HANDLE)
_sig(k32.CloseHandle, wt.BOOL, HANDLE)
_sig(k32.OpenEventW, HANDLE, wt.DWORD, wt.BOOL, wt.LPCWSTR)
_sig(k32.FreeConsole, wt.BOOL)
_sig(gdi32.AddFontMemResourceEx, HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, ctypes.POINTER(wt.DWORD))
_sig(gdi32.CreateFontW, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.DWORD,
     wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR)
_sig(gdi32.SetTextColor, wt.DWORD, HANDLE, wt.DWORD)
_sig(gdi32.SetBkColor, wt.DWORD, HANDLE, wt.DWORD)
_sig(gdi32.SetBkMode, ctypes.c_int, HANDLE, ctypes.c_int)
_sig(gdi32.CreateSolidBrush, HANDLE, wt.DWORD)
_sig(gdi32.GetTextExtentPoint32W, wt.BOOL, HANDLE, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.SIZE))
_sig(gdi32.ExcludeClipRect, ctypes.c_int, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_sig(gdi32.CreateCompatibleDC, HANDLE, HANDLE)
_sig(gdi32.CreateCompatibleBitmap, HANDLE, HANDLE, ctypes.c_int, ctypes.c_int)
_sig(gdi32.CreateDIBSection, HANDLE, HANDLE, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), HANDLE,
     wt.DWORD)
_sig(gdi32.SelectObject, HANDLE, HANDLE, HANDLE)
_sig(gdi32.DeleteObject, wt.BOOL, HANDLE)
_sig(gdi32.DeleteDC, wt.BOOL, HANDLE)
_sig(gdi32.BitBlt, wt.BOOL, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, HANDLE, ctypes.c_int,
     ctypes.c_int, wt.DWORD)
_sig(gdi32.GdiFlush, wt.BOOL)
_sig(gdi32.IntersectClipRect, ctypes.c_int, HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
_sig(gdi32.SelectClipRgn, ctypes.c_int, HANDLE, HANDLE)
_sig(dwmapi.DwmSetWindowAttribute, ctypes.c_long, HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD)
_sig(gdiplus.GdiplusStartup, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(GdiplusStartupInput),
     ctypes.c_void_p)
for _name, _args in (
        ("GdipCreateFromHDC", (HANDLE, PVP)), ("GdipSetSmoothingMode", (VP, ctypes.c_int)),
        ("GdipSetPixelOffsetMode", (VP, ctypes.c_int)), ("GdipDeleteGraphics", (VP,)),
        ("GdipCreateSolidFill", (ctypes.c_uint32, PVP)), ("GdipDeleteBrush", (VP,)),
        ("GdipFillEllipse", (VP, VP, F, F, F, F)), ("GdipCreatePath", (ctypes.c_int, PVP)),
        ("GdipAddPathArc", (VP, F, F, F, F, F, F)), ("GdipClosePathFigure", (VP,)), ("GdipFillPath", (VP, VP, VP)),
        ("GdipDeletePath", (VP,)), ("GdipCreatePen1", (ctypes.c_uint32, F, ctypes.c_int, PVP)),
        ("GdipSetPenStartCap", (VP, ctypes.c_int)), ("GdipSetPenEndCap", (VP, ctypes.c_int)),
        ("GdipDrawArc", (VP, VP, F, F, F, F, F, F)), ("GdipDeletePen", (VP,)),
        ("GdipAddPathEllipse", (VP, F, F, F, F)), ("GdipCreatePathGradientFromPath", (VP, PVP)),
        ("GdipSetPathGradientCenterColor", (VP, ctypes.c_uint32)),
        ("GdipSetPathGradientSurroundColorsWithCount", (VP, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_int))),
        ("GdipSetPathGradientSigmaBlend", (VP, F, F)), ("GdipDrawPath", (VP, VP, VP)),
        ("GdipSetClipPath", (VP, VP, ctypes.c_int)), ("GdipResetClip", (VP,)),
        ("GdipCreateLineBrush", (ctypes.POINTER(POINTF), ctypes.POINTER(POINTF), ctypes.c_uint32, ctypes.c_uint32,
                                 ctypes.c_int, PVP)),
        ("GdipSetLinePresetBlend", (VP, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(F), ctypes.c_int)),
        ("GdipCreateBitmapFromScan0", (ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, PVP)),
        ("GdipDrawImageRect", (VP, VP, F, F, F, F)), ("GdipSetInterpolationMode", (VP, ctypes.c_int)),
        ("GdipDisposeImage", (VP,)), ("GdipGetImageGraphicsContext", (VP, PVP)),
        ("GdipSetClipRectI", (VP, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int))):
    _sig(getattr(gdiplus, _name), ctypes.c_int, *_args)
try:
    shcore = ctypes.WinDLL("shcore")
    _sig(shcore.GetDpiForMonitor, ctypes.c_long, HANDLE, ctypes.c_int, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT))
except (OSError, AttributeError):
    shcore = None


# ---- texts (the four other languages: STRINGS_MORE, further down)
STRINGS = {
    "en": {
        "status_showing": "On the keyboard now", "status_waiting": "Shows after {delay} without input",
        "status_always": "Always on the keyboard", "status_manual": "Shows with {hotkey}",
        "status_manual_none": "Shows from this panel only", "status_paused": "Paused until {time}",
        "status_off": "Clock off", "status_hidden_app": "Hidden while an app is full screen",
        "status_no_keyboard": "Keyboard not found",
        "open_app": "Open Keyboard Clock", "clock": "Clock", "show_now": "Show it now",
        "pause_hour": "Pause for an hour", "resume": "Resume", "display": "Display", "brightness": "Brightness",
        "mode_time": "Time", "mode_time_date": "Time and date", "mode_scroll": "Scrolling text", "mode_mixed": "Mixed",
        "mode_custom": "Custom",
        "start_windows": "Start with Windows", "about": "About", "updates": "Check for updates",
        "up_to_date": "Up to date", "check_failed": "Check failed", "auto_check": "Check automatically",
        "update_to": "Update to {version}", "update_title": "Keyboard Clock {version} is available",
        "update_text": "Click here to install it.", "update_downloading": "Downloading version {version}…",
        "update_installing": "Installing the new version…", "update_failed": "The update failed: {error}",
        "made_by": "Made by {author}", "star": "Star it on GitHub", "open_log": "Open the log", "quit": "Quit",
        "app_quit": "Quit Keyboard Clock",
        "app_background": "Keyboard Clock keeps running in the background. Click its icon next to the clock to come back.",
        "already": "Keyboard Clock is already running: its icon is next to the clock.",
        "nav_clock": "Clock", "nav_look": "Look", "nav_when": "When", "nav_font": "Font", "nav_keyboard": "Keyboard",
        "nav_settings": "Settings", "nav_about": "About",
        "clock_sub": "What your keyboard shows while you are away.",
        "live_preview": "Live preview", "show_keyboard": "Show on the keyboard",
        "screen_secs": "Each screen stays", "transition": "Transition", "tr_fade": "Fade", "tr_slide": "Slide",
        "tr_wipe": "Wipe", "tr_dissolve": "Dissolve", "tr_none": "None",
        "scroll_text": "Scrolling text", "scroll_speed": "Speed", "scroll_smooth": "Smooth scrolling",
        "scroll_smooth_desc": "Off: the text moves key by key, sharper on the keys",
        "text_time": "Time", "text_time_date": "Time and date", "text_date": "Date", "text_seconds": "Time with seconds",
        "text_custom": "Your own text…", "text_dialog": "Scrolling text",
        "text_prompt": "Text to scroll on the keyboard:",
        "text_hint": "Live values: {time} {hours} {minutes} {seconds} {weekday} {date} {day} {month} {year}",
        "ok": "OK", "cancel": "Cancel",
        "formats": "Formats", "hour12": "12-hour clock", "leading_zero": "Leading zero",
        "leading_zero_desc": "09:05 rather than 9:05", "seconds": "Seconds", "sec_block": "Key block",
        "sec_bar": "Bar", "sec_numpad": "Numpad", "sec_beat": "Beat", "sec_off": "None",
        "look_sub": "Colors, background and effects.", "themes": "Themes",
        "theme_neon": "Neon", "theme_matrix": "Matrix", "theme_sunset": "Sunset", "theme_ocean": "Ocean",
        "theme_white": "White", "theme_rainbow": "Rainbow", "theme_daylight": "Colors of the day",
        "theme_night_red": "Night red",
        "colors": "Colors", "style": "Style", "style_solid": "A color per part", "style_gradient": "Gradient",
        "style_flow": "Flowing gradient", "style_rainbow": "Rainbow", "style_daytime": "Colors of the day",
        "style_digits": "A color per digit",
        "style_rainbow_desc": "Every color, moving slowly across the keys.",
        "style_daytime_desc": "Orange in the morning, cyan in the day, purple at night: the color follows the hour.",
        "role_hours": "Hours", "role_minutes": "Minutes", "role_date": "Date", "role_seconds": "Seconds",
        "role_text": "Text", "digit_left": "Left digit", "digit_right": "Right digit",
        "color_hue": "Hue", "color_sat": "Saturation",
        "background": "Background", "bg_off": "Off", "bg_dim": "Dim", "bg_gradient": "Gradient",
        "bg_breathe": "Breathing", "bg_twinkle": "Stars", "bg_level": "Background",
        "bg_gradient_desc": "The other keys take the colors of the gradient above, dimmed.",
        "effects": "Effects", "chime": "Chime", "chime_off": "None", "chime_hour": "Every hour",
        "chime_half": "Every half hour",
        "when_sub": "When the clock takes over your keyboard's lighting.", "show_clock": "Show the clock",
        "when_idle": "When I'm away", "when_always": "Always", "when_manual": "Shortcut only", "after": "After",
        "on_lock": "As soon as the PC is locked", "on_lock_desc": "Win+L shows it right away",
        "hide_fullscreen": "Not during full-screen games and videos",
        "hide_fullscreen_desc": "Their own lighting stays on",
        "hotkey": "Shortcut", "hotkey_desc": "Shows or hides the clock from anywhere", "hotkey_none": "None",
        "off_after": "Then turn the keys off after", "off_after_desc": "The keyboard stays dark until you come back",
        "never": "Never", "night": "Night", "night_hours": "Night hours", "night_from": "From", "night_to": "to",
        "at_night": "At night", "night_dim": "Dimmed", "night_red": "Red", "night_dark": "Keys off",
        "night_brightness": "Night brightness",
        "font_sub": "Draw each digit key by key, on the left and on the right: the function keys sit differently "
                    "above each.",
        "font_use": "Use my digits", "font_use_desc": "Off: the built-in digits", "font_digit": "Digit",
        "font_left": "Left", "font_right": "Right",
        "font_hint": "Click a key to light it or clear it. Each side has its own keys.",
        "font_reset": "Reset this digit", "font_copy": "Copy to the other side", "font_reset_all": "Reset all",
        "keyboard_sub": "The keyboard Keyboard Clock drives.", "kb_ghub": "Logitech G (G HUB)",
        "kb_ok": "Ready", "kb_missing": "G HUB not found",
        "kb_help": "In G HUB, open Settings and turn on “Allow games & applications to control my lighting”.",
        "kb_layout": "Layout", "model_auto": "Automatic", "model_tkl-iso": "Tenkeyless, ISO (Europe)",
        "model_tkl-ansi": "Tenkeyless, ANSI (US)", "model_full-iso": "Full size, ISO (Europe)",
        "model_full-ansi": "Full size, ANSI (US)",
        "kb_test": "Test my keyboard", "kb_test_desc": "Shows 0 to 9 on both sides",
        "kb_test_button": "Test", "kb_more": "Other brands",
        "kb_more_desc": "Windows Dynamic Lighting and OpenRGB keyboards are coming.",
        "settings_sub": "Startup, updates and language.",
        "settings_start_desc": "Runs in the background, next to the clock", "settings_updates": "Updates",
        "settings_new": "Version {version} is available", "settings_check_now": "Check now",
        "settings_check_desc": "Once a day, from GitHub", "settings_lang": "Language",
        "settings_lang_label": "Language of the app", "lang_auto": "Windows language", "settings_help": "Help",
        "settings_open": "Open", "settings_log_desc": "What Keyboard Clock did, to report a problem",
        "about_version": "Version {version}",
        "about_tagline": "Your keyboard shows the time while you are away, in big digits drawn on its keys. "
                         "Free and open source.",
        "about_site": "Website", "about_source": "Source code", "about_issue": "Report a problem",
        "about_license": "MIT License. Logitech and G HUB are trademarks of Logitech; Keyboard Clock is not "
                         "affiliated with Logitech.",
        "secs_fmt": "{n} s", "mins_fmt": "{n} min", "hours_fmt": "{n} h",
    },
    "fr": {
        "status_showing": "Affichée sur le clavier", "status_waiting": "S'affiche après {delay} d'inactivité",
        "status_always": "Toujours sur le clavier", "status_manual": "S'affiche avec {hotkey}",
        "status_manual_none": "S'affiche depuis ce panneau", "status_paused": "En pause jusqu'à {time}",
        "status_off": "Horloge désactivée", "status_hidden_app": "Masquée : une app est en plein écran",
        "status_no_keyboard": "Clavier introuvable",
        "open_app": "Ouvrir Keyboard Clock", "clock": "Horloge", "show_now": "L'afficher maintenant",
        "pause_hour": "Pause d'une heure", "resume": "Reprendre", "display": "Affichage", "brightness": "Luminosité",
        "mode_time": "Heure", "mode_time_date": "Heure et date", "mode_scroll": "Texte qui défile",
        "mode_mixed": "Mixte", "mode_custom": "Personnalisé",
        "start_windows": "Démarrer avec Windows", "about": "À propos", "updates": "Rechercher des mises à jour",
        "up_to_date": "À jour", "check_failed": "Échec de la vérification", "auto_check": "Vérifier automatiquement",
        "update_to": "Mettre à jour vers {version}", "update_title": "Keyboard Clock {version} est disponible",
        "update_text": "Cliquez ici pour l'installer.", "update_downloading": "Téléchargement de la version {version}…",
        "update_installing": "Installation de la nouvelle version…", "update_failed": "La mise à jour a échoué : {error}",
        "made_by": "Créé par {author}", "star": "Une étoile sur GitHub", "open_log": "Ouvrir le journal",
        "quit": "Quitter", "app_quit": "Quitter Keyboard Clock",
        "app_background": "Keyboard Clock continue en arrière-plan. Cliquez sur son icône près de l'horloge pour revenir.",
        "already": "Keyboard Clock est déjà lancé : son icône est à côté de l'horloge.",
        "nav_clock": "Horloge", "nav_look": "Apparence", "nav_when": "Quand", "nav_font": "Police",
        "nav_keyboard": "Clavier", "nav_settings": "Réglages", "nav_about": "À propos",
        "clock_sub": "Ce que votre clavier affiche quand vous vous absentez.",
        "live_preview": "Aperçu en direct", "show_keyboard": "Afficher sur le clavier",
        "screen_secs": "Durée de chaque écran", "transition": "Transition", "tr_fade": "Fondu", "tr_slide": "Glisser",
        "tr_wipe": "Balayage", "tr_dissolve": "Dissolution", "tr_none": "Aucune",
        "scroll_text": "Texte qui défile", "scroll_speed": "Vitesse", "scroll_smooth": "Défilement fluide",
        "scroll_smooth_desc": "Désactivé : le texte avance touche par touche, plus net sur le clavier",
        "text_time": "Heure", "text_time_date": "Heure et date", "text_date": "Date",
        "text_seconds": "Heure avec secondes", "text_custom": "Votre texte…", "text_dialog": "Texte qui défile",
        "text_prompt": "Texte à faire défiler sur le clavier :",
        "text_hint": "Valeurs en direct : {time} {hours} {minutes} {seconds} {weekday} {date} {day} {month} {year}",
        "ok": "OK", "cancel": "Annuler",
        "formats": "Formats", "hour12": "Format 12 heures", "leading_zero": "Zéro devant",
        "leading_zero_desc": "09:05 plutôt que 9:05", "seconds": "Secondes", "sec_block": "Bloc",
        "sec_bar": "Barre", "sec_numpad": "Pavé num.", "sec_beat": "Battement", "sec_off": "Aucune",
        "look_sub": "Couleurs, fond et effets.", "themes": "Thèmes",
        "theme_neon": "Néon", "theme_matrix": "Matrix", "theme_sunset": "Coucher de soleil", "theme_ocean": "Océan",
        "theme_white": "Blanc", "theme_rainbow": "Arc-en-ciel", "theme_daylight": "Couleurs du jour",
        "theme_night_red": "Rouge nuit",
        "colors": "Couleurs", "style": "Style", "style_solid": "Une couleur par élément", "style_gradient": "Dégradé",
        "style_flow": "Dégradé qui coule", "style_rainbow": "Arc-en-ciel", "style_daytime": "Couleurs du jour",
        "style_digits": "Une couleur par chiffre",
        "style_rainbow_desc": "Toutes les couleurs, qui glissent lentement sur les touches.",
        "style_daytime_desc": "Orange le matin, cyan la journée, violet la nuit : la couleur suit l'heure.",
        "role_hours": "Heures", "role_minutes": "Minutes", "role_date": "Date", "role_seconds": "Secondes",
        "role_text": "Texte", "digit_left": "Chiffre de gauche", "digit_right": "Chiffre de droite",
        "color_hue": "Teinte", "color_sat": "Saturation",
        "background": "Fond", "bg_off": "Éteint", "bg_dim": "Tamisé", "bg_gradient": "Dégradé",
        "bg_breathe": "Respiration", "bg_twinkle": "Étoiles", "bg_level": "Luminosité du fond",
        "bg_gradient_desc": "Les autres touches prennent les couleurs du dégradé ci-dessus, atténuées.",
        "effects": "Effets", "chime": "Carillon", "chime_off": "Aucun", "chime_hour": "Toutes les heures",
        "chime_half": "Toutes les demi-heures",
        "when_sub": "Quand l'horloge prend la main sur l'éclairage du clavier.", "show_clock": "Afficher l'horloge",
        "when_idle": "Quand je m'absente", "when_always": "Toujours", "when_manual": "Avec le raccourci",
        "after": "Après",
        "on_lock": "Dès que le PC est verrouillé", "on_lock_desc": "Win+L l'affiche tout de suite",
        "hide_fullscreen": "Pas pendant les jeux et vidéos en plein écran",
        "hide_fullscreen_desc": "Leur propre éclairage reste affiché",
        "hotkey": "Raccourci", "hotkey_desc": "Affiche ou masque l'horloge depuis n'importe où",
        "hotkey_none": "Aucun",
        "off_after": "Puis éteindre les touches après", "off_after_desc": "Le clavier reste noir jusqu'à votre retour",
        "never": "Jamais", "night": "Nuit", "night_hours": "Heures de nuit", "night_from": "De", "night_to": "à",
        "at_night": "La nuit", "night_dim": "Tamisée", "night_red": "En rouge", "night_dark": "Touches éteintes",
        "night_brightness": "Luminosité de nuit",
        "font_sub": "Dessinez chaque chiffre touche par touche, à gauche et à droite : les touches F ne tombent pas "
                    "pareil au-dessus des deux.",
        "font_use": "Utiliser mes chiffres", "font_use_desc": "Désactivé : les chiffres d'origine",
        "font_digit": "Chiffre", "font_left": "Gauche", "font_right": "Droite",
        "font_hint": "Cliquez sur une touche pour l'allumer ou l'éteindre. Chaque côté a ses propres touches.",
        "font_reset": "Réinitialiser ce chiffre", "font_copy": "Copier de l'autre côté",
        "font_reset_all": "Tout réinitialiser",
        "keyboard_sub": "Le clavier que Keyboard Clock pilote.", "kb_ghub": "Logitech G (G HUB)",
        "kb_ok": "Prêt", "kb_missing": "G HUB introuvable",
        "kb_help": "Dans G HUB, ouvrez les Paramètres et activez « Autoriser les jeux et applications à contrôler "
                   "mon éclairage ».",
        "kb_layout": "Disposition", "model_auto": "Automatique", "model_tkl-iso": "Sans pavé numérique, ISO (Europe)",
        "model_tkl-ansi": "Sans pavé numérique, ANSI (US)", "model_full-iso": "Complet, ISO (Europe)",
        "model_full-ansi": "Complet, ANSI (US)",
        "kb_test": "Tester mon clavier", "kb_test_desc": "Affiche 0 à 9 des deux côtés", "kb_test_button": "Tester",
        "kb_more": "Autres marques",
        "kb_more_desc": "Les claviers Éclairage dynamique de Windows et OpenRGB arrivent bientôt.",
        "settings_sub": "Démarrage, mises à jour et langue.",
        "settings_start_desc": "Tourne en arrière-plan, près de l'horloge", "settings_updates": "Mises à jour",
        "settings_new": "La version {version} est disponible", "settings_check_now": "Vérifier",
        "settings_check_desc": "Une fois par jour, sur GitHub", "settings_lang": "Langue",
        "settings_lang_label": "Langue de l'application", "lang_auto": "Langue de Windows", "settings_help": "Aide",
        "settings_open": "Ouvrir", "settings_log_desc": "Ce qu'a fait Keyboard Clock, pour signaler un problème",
        "about_version": "Version {version}",
        "about_tagline": "Votre clavier affiche l'heure quand vous vous absentez, en gros chiffres dessinés sur ses "
                         "touches. Gratuit et open source.",
        "about_site": "Site web", "about_source": "Code source", "about_issue": "Signaler un problème",
        "about_license": "Licence MIT. Logitech et G HUB sont des marques de Logitech ; Keyboard Clock n'est pas "
                         "affilié à Logitech.",
        "secs_fmt": "{n} s", "mins_fmt": "{n} min", "hours_fmt": "{n} h",
    },
    "es": {
        "status_showing": "Ahora en el teclado", "status_waiting": "Aparece tras {delay} sin actividad",
        "status_always": "Siempre en el teclado", "status_manual": "Aparece con {hotkey}",
        "status_manual_none": "Solo aparece desde este panel", "status_paused": "En pausa hasta las {time}",
        "status_off": "Reloj desactivado", "status_hidden_app": "Oculto: una app está en pantalla completa",
        "status_no_keyboard": "Teclado no encontrado",
        "open_app": "Abrir Keyboard Clock", "clock": "Reloj", "show_now": "Mostrarlo ahora",
        "pause_hour": "Pausar una hora", "resume": "Reanudar", "display": "Visualización", "brightness": "Brillo",
        "mode_time": "Hora", "mode_time_date": "Hora y fecha", "mode_scroll": "Texto desplazable", "mode_mixed": "Mixto",
        "mode_custom": "Personalizado",
        "start_windows": "Iniciar con Windows", "about": "Acerca de", "updates": "Buscar actualizaciones",
        "up_to_date": "Actualizado", "check_failed": "Error al buscar", "auto_check": "Buscar automáticamente",
        "update_to": "Actualizar a {version}", "update_title": "Keyboard Clock {version} está disponible",
        "update_text": "Haz clic aquí para instalarlo.", "update_downloading": "Descargando la versión {version}…",
        "update_installing": "Instalando la nueva versión…", "update_failed": "La actualización falló: {error}",
        "made_by": "Creado por {author}", "star": "Dar una estrella en GitHub", "open_log": "Abrir registro",
        "quit": "Salir", "app_quit": "Salir de Keyboard Clock",
        "app_background": "Keyboard Clock sigue funcionando en segundo plano. Haz clic en su icono junto al reloj "
                          "para volver.",
        "already": "Keyboard Clock ya está en marcha: su icono está junto al reloj.",
        "nav_clock": "Reloj", "nav_look": "Aspecto", "nav_when": "Cuándo", "nav_font": "Fuente",
        "nav_keyboard": "Teclado", "nav_settings": "Configuración", "nav_about": "Acerca de",
        "clock_sub": "Lo que muestra tu teclado cuando no estás.",
        "live_preview": "Vista previa en vivo", "show_keyboard": "Mostrar en el teclado",
        "screen_secs": "Cada pantalla dura", "transition": "Transición", "tr_fade": "Fundido", "tr_slide": "Deslizar",
        "tr_wipe": "Barrido", "tr_dissolve": "Disolver", "tr_none": "Ninguna",
        "scroll_text": "Texto desplazable", "scroll_speed": "Velocidad", "scroll_smooth": "Desplazamiento suave",
        "scroll_smooth_desc": "Desactivado: el texto avanza tecla a tecla, más nítido en las teclas",
        "text_time": "Hora", "text_time_date": "Hora y fecha", "text_date": "Fecha",
        "text_seconds": "Hora con segundos", "text_custom": "Tu propio texto…", "text_dialog": "Texto desplazable",
        "text_prompt": "Texto que se desplazará por el teclado:",
        "text_hint": "Valores en vivo: {time} {hours} {minutes} {seconds} {weekday} {date} {day} {month} {year}",
        "ok": "Aceptar", "cancel": "Cancelar",
        "formats": "Formatos", "hour12": "Formato de 12 horas", "leading_zero": "Cero inicial",
        "leading_zero_desc": "09:05 en lugar de 9:05", "seconds": "Segundos", "sec_block": "Bloque",
        "sec_bar": "Barra", "sec_numpad": "Teclado num.", "sec_beat": "Pulso", "sec_off": "Ninguno",
        "look_sub": "Colores, fondo y efectos.", "themes": "Temas",
        "theme_neon": "Neón", "theme_matrix": "Matrix", "theme_sunset": "Atardecer", "theme_ocean": "Océano",
        "theme_white": "Blanco", "theme_rainbow": "Arcoíris", "theme_daylight": "Colores del día",
        "theme_night_red": "Rojo noche",
        "colors": "Colores", "style": "Estilo", "style_solid": "Un color por parte", "style_gradient": "Degradado",
        "style_flow": "Degradado que fluye", "style_rainbow": "Arcoíris", "style_daytime": "Colores del día",
        "style_digits": "Un color por dígito",
        "style_rainbow_desc": "Todos los colores, deslizándose despacio por las teclas.",
        "style_daytime_desc": "Naranja por la mañana, cian de día, violeta de noche: el color sigue la hora.",
        "role_hours": "Horas", "role_minutes": "Minutos", "role_date": "Fecha", "role_seconds": "Segundos",
        "role_text": "Texto", "digit_left": "Dígito izquierdo", "digit_right": "Dígito derecho",
        "color_hue": "Tono", "color_sat": "Saturación",
        "background": "Fondo", "bg_off": "Apagado", "bg_dim": "Tenue", "bg_gradient": "Degradado",
        "bg_breathe": "Respiración", "bg_twinkle": "Estrellas", "bg_level": "Brillo del fondo",
        "bg_gradient_desc": "Las demás teclas toman los colores del degradado de arriba, atenuados.",
        "effects": "Efectos", "chime": "Campanada", "chime_off": "Ninguna", "chime_hour": "Cada hora",
        "chime_half": "Cada media hora",
        "when_sub": "Cuándo el reloj toma el control de la iluminación de tu teclado.",
        "show_clock": "Mostrar el reloj",
        "when_idle": "Si no estoy", "when_always": "Siempre", "when_manual": "Con el atajo", "after": "Después de",
        "on_lock": "En cuanto se bloquea el PC", "on_lock_desc": "Win+L lo muestra al instante",
        "hide_fullscreen": "No durante juegos y vídeos en pantalla completa",
        "hide_fullscreen_desc": "Mantienen su propia iluminación",
        "hotkey": "Atajo", "hotkey_desc": "Muestra u oculta el reloj desde cualquier lugar", "hotkey_none": "Ninguno",
        "off_after": "Luego apagar las teclas tras", "off_after_desc": "El teclado queda a oscuras hasta que vuelvas",
        "never": "Nunca", "night": "Noche", "night_hours": "Horario nocturno", "night_from": "De", "night_to": "a",
        "at_night": "Por la noche", "night_dim": "Atenuado", "night_red": "En rojo", "night_dark": "Apagado",
        "night_brightness": "Brillo de noche",
        "font_sub": "Dibuja cada dígito tecla a tecla, a la izquierda y a la derecha: las teclas de función no "
                    "quedan igual encima de cada uno.",
        "font_use": "Usar mis dígitos", "font_use_desc": "Desactivado: los dígitos de serie", "font_digit": "Dígito",
        "font_left": "Izquierda", "font_right": "Derecha",
        "font_hint": "Haz clic en una tecla para encenderla o apagarla. Cada lado tiene sus propias teclas.",
        "font_reset": "Restablecer dígito", "font_copy": "Copiar al otro lado", "font_reset_all": "Restablecer todo",
        "keyboard_sub": "El teclado que controla Keyboard Clock.", "kb_ghub": "Logitech G (G HUB)",
        "kb_ok": "Listo", "kb_missing": "G HUB no encontrado",
        "kb_help": "En G HUB, abre la Configuración y activa «Permitir que los juegos y aplicaciones controlen mi "
                   "iluminación».",
        "kb_layout": "Distribución", "model_auto": "Automático",
        "model_tkl-iso": "Sin teclado numérico, ISO (Europa)", "model_tkl-ansi": "Sin teclado numérico, ANSI (EE. UU.)",
        "model_full-iso": "Completo, ISO (Europa)", "model_full-ansi": "Completo, ANSI (EE. UU.)",
        "kb_test": "Probar mi teclado", "kb_test_desc": "Muestra del 0 al 9 en ambos lados",
        "kb_test_button": "Probar", "kb_more": "Otras marcas",
        "kb_more_desc": "Pronto llegarán los teclados con Iluminación dinámica de Windows y OpenRGB.",
        "settings_sub": "Inicio, actualizaciones e idioma.",
        "settings_start_desc": "Funciona en segundo plano, junto al reloj", "settings_updates": "Actualizaciones",
        "settings_new": "La versión {version} está disponible", "settings_check_now": "Buscar",
        "settings_check_desc": "Una vez al día, desde GitHub", "settings_lang": "Idioma",
        "settings_lang_label": "Idioma de la app", "lang_auto": "Idioma de Windows", "settings_help": "Ayuda",
        "settings_open": "Abrir", "settings_log_desc": "Lo que ha hecho Keyboard Clock, para informar de un problema",
        "about_version": "Versión {version}",
        "about_tagline": "Tu teclado muestra la hora cuando no estás, con grandes dígitos dibujados en sus teclas. "
                         "Gratuito y de código abierto.",
        "about_site": "Sitio web", "about_source": "Código fuente", "about_issue": "Informar de un problema",
        "about_license": "Licencia MIT. Logitech y G HUB son marcas comerciales de Logitech; Keyboard Clock no está "
                         "afiliado a Logitech.",
        "secs_fmt": "{n} s", "mins_fmt": "{n} min", "hours_fmt": "{n} h",
    },
    "de": {
        "status_showing": "Gerade auf der Tastatur", "status_waiting": "Erscheint nach {delay} ohne Eingabe",
        "status_always": "Immer auf der Tastatur", "status_manual": "Erscheint mit {hotkey}",
        "status_manual_none": "Erscheint nur über dieses Panel", "status_paused": "Pausiert bis {time}",
        "status_off": "Uhr aus", "status_hidden_app": "Ausgeblendet: Eine App läuft im Vollbild",
        "status_no_keyboard": "Tastatur nicht gefunden",
        "open_app": "Keyboard Clock öffnen", "clock": "Uhr", "show_now": "Jetzt anzeigen",
        "pause_hour": "Eine Stunde pausieren", "resume": "Fortsetzen", "display": "Anzeige", "brightness": "Helligkeit",
        "mode_time": "Uhrzeit", "mode_time_date": "Uhrzeit und Datum", "mode_scroll": "Lauftext",
        "mode_mixed": "Gemischt", "mode_custom": "Individuell",
        "start_windows": "Mit Windows starten", "about": "Info", "updates": "Nach Updates suchen",
        "up_to_date": "Aktuell", "check_failed": "Suche fehlgeschlagen", "auto_check": "Automatisch suchen",
        "update_to": "Auf {version} aktualisieren", "update_title": "Keyboard Clock {version} ist verfügbar",
        "update_text": "Zum Installieren hier klicken.",
        "update_downloading": "Version {version} wird heruntergeladen …",
        "update_installing": "Die neue Version wird installiert …",
        "update_failed": "Das Update ist fehlgeschlagen: {error}",
        "made_by": "Erstellt von {author}", "star": "Auf GitHub einen Stern geben", "open_log": "Protokoll öffnen",
        "quit": "Beenden", "app_quit": "Keyboard Clock beenden",
        "app_background": "Keyboard Clock läuft im Hintergrund weiter. Klicke auf das Symbol neben der Uhr, um "
                          "zurückzukehren.",
        "already": "Keyboard Clock läuft bereits: Das Symbol befindet sich neben der Uhr.",
        "nav_clock": "Uhr", "nav_look": "Aussehen", "nav_when": "Wann", "nav_font": "Schrift",
        "nav_keyboard": "Tastatur", "nav_settings": "Einstellungen", "nav_about": "Info",
        "clock_sub": "Was deine Tastatur zeigt, während du weg bist.",
        "live_preview": "Live-Vorschau", "show_keyboard": "Auf der Tastatur zeigen",
        "screen_secs": "Jede Anzeige bleibt", "transition": "Übergang", "tr_fade": "Überblenden",
        "tr_slide": "Schieben", "tr_wipe": "Wischen", "tr_dissolve": "Auflösen", "tr_none": "Ohne",
        "scroll_text": "Lauftext", "scroll_speed": "Tempo", "scroll_smooth": "Flüssiges Scrollen",
        "scroll_smooth_desc": "Aus: Der Text springt Taste für Taste weiter, schärfer auf den Tasten",
        "text_time": "Uhrzeit", "text_time_date": "Uhrzeit und Datum", "text_date": "Datum",
        "text_seconds": "Uhrzeit mit Sekunden", "text_custom": "Eigener Text …", "text_dialog": "Lauftext",
        "text_prompt": "Text, der über die Tastatur laufen soll:",
        "text_hint": "Live-Werte: {time} {hours} {minutes} {seconds} {weekday} {date} {day} {month} {year}",
        "ok": "OK", "cancel": "Abbrechen",
        "formats": "Formate", "hour12": "12-Stunden-Format", "leading_zero": "Führende Null",
        "leading_zero_desc": "09:05 statt 9:05", "seconds": "Sekunden", "sec_block": "Tastenblock",
        "sec_bar": "Balken", "sec_numpad": "Ziffernblock", "sec_beat": "Puls", "sec_off": "Keine",
        "look_sub": "Farben, Hintergrund und Effekte.", "themes": "Designs",
        "theme_neon": "Neon", "theme_matrix": "Matrix", "theme_sunset": "Sonnenuntergang", "theme_ocean": "Ozean",
        "theme_white": "Weiß", "theme_rainbow": "Regenbogen", "theme_daylight": "Farben des Tages",
        "theme_night_red": "Nachtrot",
        "colors": "Farben", "style": "Stil", "style_solid": "Eine Farbe pro Teil", "style_gradient": "Verlauf",
        "style_flow": "Fließender Verlauf", "style_rainbow": "Regenbogen", "style_daytime": "Farben des Tages",
        "style_digits": "Eine Farbe pro Ziffer",
        "style_rainbow_desc": "Alle Farben, die langsam über die Tasten wandern.",
        "style_daytime_desc": "Morgens Orange, tagsüber Cyan, nachts Violett: Die Farbe folgt der Uhrzeit.",
        "role_hours": "Stunden", "role_minutes": "Minuten", "role_date": "Datum", "role_seconds": "Sekunden",
        "role_text": "Text", "digit_left": "Linke Ziffer", "digit_right": "Rechte Ziffer",
        "color_hue": "Farbton", "color_sat": "Sättigung",
        "background": "Hintergrund", "bg_off": "Aus", "bg_dim": "Gedimmt", "bg_gradient": "Verlauf",
        "bg_breathe": "Atmen", "bg_twinkle": "Sterne", "bg_level": "Hintergrund",
        "bg_gradient_desc": "Die übrigen Tasten übernehmen die Farben des Verlaufs oben, gedimmt.",
        "effects": "Effekte", "chime": "Glockenschlag", "chime_off": "Aus", "chime_hour": "Stündlich",
        "chime_half": "Halbstündlich",
        "when_sub": "Wann die Uhr die Beleuchtung deiner Tastatur übernimmt.", "show_clock": "Uhr anzeigen",
        "when_idle": "Wenn ich weg bin", "when_always": "Immer", "when_manual": "Per Kürzel", "after": "Nach",
        "on_lock": "Sobald der PC gesperrt wird", "on_lock_desc": "Win+L zeigt sie sofort an",
        "hide_fullscreen": "Nicht bei Spielen und Videos im Vollbild",
        "hide_fullscreen_desc": "Ihre eigene Beleuchtung bleibt an",
        "hotkey": "Tastenkürzel", "hotkey_desc": "Blendet die Uhr von überall ein oder aus", "hotkey_none": "Keins",
        "off_after": "Dann die Tasten ausschalten nach",
        "off_after_desc": "Die Tastatur bleibt dunkel, bis du zurück bist",
        "never": "Nie", "night": "Nacht", "night_hours": "Nachtzeit", "night_from": "Von", "night_to": "bis",
        "at_night": "Nachts", "night_dim": "Gedimmt", "night_red": "Rot", "night_dark": "Tasten aus",
        "night_brightness": "Helligkeit nachts",
        "font_sub": "Zeichne jede Ziffer Taste für Taste, links und rechts: Die Funktionstasten sitzen über beiden "
                    "Seiten anders.",
        "font_use": "Meine Ziffern verwenden", "font_use_desc": "Aus: die eingebauten Ziffern", "font_digit": "Ziffer",
        "font_left": "Links", "font_right": "Rechts",
        "font_hint": "Klicke auf eine Taste, um sie ein- oder auszuschalten. Jede Seite hat ihre eigenen Tasten.",
        "font_reset": "Ziffer zurücksetzen", "font_copy": "Auf andere Seite kopieren",
        "font_reset_all": "Alle zurücksetzen",
        "keyboard_sub": "Die Tastatur, die Keyboard Clock steuert.", "kb_ghub": "Logitech G (G HUB)",
        "kb_ok": "Bereit", "kb_missing": "G HUB nicht gefunden",
        "kb_help": "Öffne in G HUB die Einstellungen und aktiviere „Spielen und Anwendungen erlauben, meine "
                   "Beleuchtung zu steuern“.",
        "kb_layout": "Layout", "model_auto": "Automatisch",
        "model_tkl-iso": "Ohne Ziffernblock, ISO (Europa)", "model_tkl-ansi": "Ohne Ziffernblock, ANSI (USA)",
        "model_full-iso": "Volle Größe, ISO (Europa)", "model_full-ansi": "Volle Größe, ANSI (USA)",
        "kb_test": "Meine Tastatur testen", "kb_test_desc": "Zeigt 0 bis 9 auf beiden Seiten",
        "kb_test_button": "Testen", "kb_more": "Andere Marken",
        "kb_more_desc": "Tastaturen für die dynamische Beleuchtung von Windows und für OpenRGB folgen bald.",
        "settings_sub": "Start, Updates und Sprache.",
        "settings_start_desc": "Läuft im Hintergrund, neben der Uhr", "settings_updates": "Updates",
        "settings_new": "Version {version} ist verfügbar", "settings_check_now": "Suchen",
        "settings_check_desc": "Einmal am Tag, über GitHub", "settings_lang": "Sprache",
        "settings_lang_label": "Sprache der App", "lang_auto": "Windows-Sprache", "settings_help": "Hilfe",
        "settings_open": "Öffnen", "settings_log_desc": "Was Keyboard Clock getan hat, um ein Problem zu melden",
        "about_version": "Version {version}",
        "about_tagline": "Deine Tastatur zeigt die Uhrzeit, während du weg bist, in großen Ziffern auf ihren Tasten. "
                         "Kostenlos und quelloffen.",
        "about_site": "Website", "about_source": "Quellcode", "about_issue": "Problem melden",
        "about_license": "MIT-Lizenz. Logitech und G HUB sind Marken von Logitech; Keyboard Clock steht in keiner "
                         "Verbindung zu Logitech.",
        "secs_fmt": "{n} Sek.", "mins_fmt": "{n} Min.", "hours_fmt": "{n} Std.",
    },
    "it": {
        "status_showing": "Ora sulla tastiera", "status_waiting": "Appare dopo {delay} di inattività",
        "status_always": "Sempre sulla tastiera", "status_manual": "Appare con {hotkey}",
        "status_manual_none": "Appare solo da questo pannello", "status_paused": "In pausa fino alle {time}",
        "status_off": "Orologio disattivato", "status_hidden_app": "Nascosto: un'app è a schermo intero",
        "status_no_keyboard": "Tastiera non trovata",
        "open_app": "Apri Keyboard Clock", "clock": "Orologio", "show_now": "Mostralo ora",
        "pause_hour": "Pausa di un'ora", "resume": "Riprendi", "display": "Visualizzazione", "brightness": "Luminosità",
        "mode_time": "Ora", "mode_time_date": "Ora e data", "mode_scroll": "Testo scorrevole", "mode_mixed": "Misto",
        "mode_custom": "Personalizzato",
        "start_windows": "Avvia con Windows", "about": "Informazioni", "updates": "Controlla aggiornamenti",
        "up_to_date": "Aggiornato", "check_failed": "Controllo non riuscito", "auto_check": "Controlla automaticamente",
        "update_to": "Aggiorna alla {version}", "update_title": "Keyboard Clock {version} è disponibile",
        "update_text": "Fai clic qui per installarlo.", "update_downloading": "Download della versione {version}…",
        "update_installing": "Installazione della nuova versione…",
        "update_failed": "L'aggiornamento non è riuscito: {error}",
        "made_by": "Creato da {author}", "star": "Metti una stella su GitHub", "open_log": "Apri il log",
        "quit": "Esci", "app_quit": "Esci da Keyboard Clock",
        "app_background": "Keyboard Clock continua in background. Fai clic sulla sua icona accanto all'orologio "
                          "per tornare.",
        "already": "Keyboard Clock è già in esecuzione: la sua icona è accanto all'orologio.",
        "nav_clock": "Orologio", "nav_look": "Aspetto", "nav_when": "Quando", "nav_font": "Carattere",
        "nav_keyboard": "Tastiera", "nav_settings": "Impostazioni", "nav_about": "Informazioni",
        "clock_sub": "Cosa mostra la tastiera quando non ci sei.",
        "live_preview": "Anteprima live", "show_keyboard": "Mostra sulla tastiera",
        "screen_secs": "Ogni schermata dura", "transition": "Transizione", "tr_fade": "Dissolvenza",
        "tr_slide": "Scorrimento", "tr_wipe": "Tendina", "tr_dissolve": "Dissolvi", "tr_none": "Nessuna",
        "scroll_text": "Testo scorrevole", "scroll_speed": "Velocità", "scroll_smooth": "Scorrimento fluido",
        "scroll_smooth_desc": "Disattivato: il testo avanza tasto per tasto, più nitido sui tasti",
        "text_time": "Ora", "text_time_date": "Ora e data", "text_date": "Data", "text_seconds": "Ora con i secondi",
        "text_custom": "Il tuo testo…", "text_dialog": "Testo scorrevole",
        "text_prompt": "Testo da far scorrere sulla tastiera:",
        "text_hint": "Valori in tempo reale: {time} {hours} {minutes} {seconds} {weekday} {date} {day} {month} {year}",
        "ok": "OK", "cancel": "Annulla",
        "formats": "Formati", "hour12": "Formato 12 ore", "leading_zero": "Zero iniziale",
        "leading_zero_desc": "09:05 invece di 9:05", "seconds": "Secondi", "sec_block": "Blocco",
        "sec_bar": "Barra", "sec_numpad": "Tastierino", "sec_beat": "Battito", "sec_off": "Nessuno",
        "look_sub": "Colori, sfondo ed effetti.", "themes": "Temi",
        "theme_neon": "Neon", "theme_matrix": "Matrix", "theme_sunset": "Tramonto", "theme_ocean": "Oceano",
        "theme_white": "Bianco", "theme_rainbow": "Arcobaleno", "theme_daylight": "Colori del giorno",
        "theme_night_red": "Rosso notte",
        "colors": "Colori", "style": "Stile", "style_solid": "Un colore per parte", "style_gradient": "Sfumatura",
        "style_flow": "Sfumatura che scorre", "style_rainbow": "Arcobaleno", "style_daytime": "Colori del giorno",
        "style_digits": "Un colore per cifra",
        "style_rainbow_desc": "Tutti i colori, che scorrono lentamente sui tasti.",
        "style_daytime_desc": "Arancione al mattino, ciano di giorno, viola di notte: il colore segue l'ora.",
        "role_hours": "Ore", "role_minutes": "Minuti", "role_date": "Data", "role_seconds": "Secondi",
        "role_text": "Testo", "digit_left": "Cifra sinistra", "digit_right": "Cifra destra",
        "color_hue": "Tonalità", "color_sat": "Saturazione",
        "background": "Sfondo", "bg_off": "Spento", "bg_dim": "Soffuso", "bg_gradient": "Sfumatura",
        "bg_breathe": "Respiro", "bg_twinkle": "Stelle", "bg_level": "Luminosità sfondo",
        "bg_gradient_desc": "Gli altri tasti prendono i colori della sfumatura qui sopra, attenuati.",
        "effects": "Effetti", "chime": "Rintocco", "chime_off": "Nessuno", "chime_hour": "Ogni ora",
        "chime_half": "Ogni mezz'ora",
        "when_sub": "Quando l'orologio prende il controllo dell'illuminazione della tastiera.",
        "show_clock": "Mostra l'orologio",
        "when_idle": "Se sono via", "when_always": "Sempre", "when_manual": "Scorciatoia", "after": "Dopo",
        "on_lock": "Appena il PC viene bloccato", "on_lock_desc": "Win+L lo mostra subito",
        "hide_fullscreen": "Non durante giochi e video a schermo intero",
        "hide_fullscreen_desc": "Mantengono la loro illuminazione",
        "hotkey": "Scorciatoia", "hotkey_desc": "Mostra o nasconde l'orologio ovunque tu sia", "hotkey_none": "Nessuna",
        "off_after": "Poi spegni i tasti dopo", "off_after_desc": "La tastiera resta spenta finché non torni",
        "never": "Mai", "night": "Notte", "night_hours": "Orario notturno", "night_from": "Dalle", "night_to": "alle",
        "at_night": "Di notte", "night_dim": "Attenuato", "night_red": "In rosso", "night_dark": "Tasti spenti",
        "night_brightness": "Luminosità di notte",
        "font_sub": "Disegna ogni cifra tasto per tasto, a sinistra e a destra: i tasti funzione non cadono allo "
                    "stesso modo sopra ciascuna.",
        "font_use": "Usa le mie cifre", "font_use_desc": "Disattivato: le cifre predefinite", "font_digit": "Cifra",
        "font_left": "Sinistra", "font_right": "Destra",
        "font_hint": "Fai clic su un tasto per accenderlo o spegnerlo. Ogni lato ha i suoi tasti.",
        "font_reset": "Ripristina cifra", "font_copy": "Copia sull'altro lato", "font_reset_all": "Ripristina tutto",
        "keyboard_sub": "La tastiera che Keyboard Clock comanda.", "kb_ghub": "Logitech G (G HUB)",
        "kb_ok": "Pronto", "kb_missing": "G HUB non trovato",
        "kb_help": "In G HUB, apri le Impostazioni e attiva «Consenti a giochi e applicazioni di controllare la mia "
                   "illuminazione».",
        "kb_layout": "Layout", "model_auto": "Automatico",
        "model_tkl-iso": "Senza tastierino, ISO (Europa)", "model_tkl-ansi": "Senza tastierino, ANSI (USA)",
        "model_full-iso": "Completa, ISO (Europa)", "model_full-ansi": "Completa, ANSI (USA)",
        "kb_test": "Prova la tastiera", "kb_test_desc": "Mostra da 0 a 9 su entrambi i lati",
        "kb_test_button": "Prova", "kb_more": "Altre marche",
        "kb_more_desc": "In arrivo le tastiere con Illuminazione dinamica di Windows e OpenRGB.",
        "settings_sub": "Avvio, aggiornamenti e lingua.",
        "settings_start_desc": "Resta in background, accanto all'orologio", "settings_updates": "Aggiornamenti",
        "settings_new": "La versione {version} è disponibile", "settings_check_now": "Controlla",
        "settings_check_desc": "Una volta al giorno, da GitHub", "settings_lang": "Lingua",
        "settings_lang_label": "Lingua dell'app", "lang_auto": "Lingua di Windows", "settings_help": "Aiuto",
        "settings_open": "Apri", "settings_log_desc": "Cosa ha fatto Keyboard Clock, per segnalare un problema",
        "about_version": "Versione {version}",
        "about_tagline": "La tastiera mostra l'ora quando non ci sei, con grandi cifre disegnate sui tasti. "
                         "Gratuito e open source.",
        "about_site": "Sito web", "about_source": "Codice sorgente", "about_issue": "Segnala un problema",
        "about_license": "Licenza MIT. Logitech e G HUB sono marchi di Logitech; Keyboard Clock non è affiliato a "
                         "Logitech.",
        "secs_fmt": "{n} s", "mins_fmt": "{n} min", "hours_fmt": "{n} h",
    },
    "pt": {
        "status_showing": "No teclado agora", "status_waiting": "Aparece após {delay} sem atividade",
        "status_always": "Sempre no teclado", "status_manual": "Aparece com {hotkey}",
        "status_manual_none": "Aparece só por este painel", "status_paused": "Pausado até {time}",
        "status_off": "Relógio desligado", "status_hidden_app": "Oculto: um app está em tela cheia",
        "status_no_keyboard": "Teclado não encontrado",
        "open_app": "Abrir o Keyboard Clock", "clock": "Relógio", "show_now": "Mostrar agora",
        "pause_hour": "Pausar por uma hora", "resume": "Retomar", "display": "Exibição", "brightness": "Brilho",
        "mode_time": "Hora", "mode_time_date": "Hora e data", "mode_scroll": "Texto rolante", "mode_mixed": "Misto",
        "mode_custom": "Personalizado",
        "start_windows": "Iniciar com o Windows", "about": "Sobre", "updates": "Verificar atualizações",
        "up_to_date": "Atualizado", "check_failed": "Falha na verificação", "auto_check": "Verificar automaticamente",
        "update_to": "Atualizar para {version}", "update_title": "Keyboard Clock {version} está disponível",
        "update_text": "Clique aqui para instalar.", "update_downloading": "Baixando a versão {version}…",
        "update_installing": "Instalando a nova versão…", "update_failed": "A atualização falhou: {error}",
        "made_by": "Criado por {author}", "star": "Dar uma estrela no GitHub", "open_log": "Abrir log",
        "quit": "Sair", "app_quit": "Sair do Keyboard Clock",
        "app_background": "O Keyboard Clock continua em segundo plano. Clique no ícone dele ao lado do relógio "
                          "para voltar.",
        "already": "O Keyboard Clock já está em execução: o ícone dele fica ao lado do relógio.",
        "nav_clock": "Relógio", "nav_look": "Aparência", "nav_when": "Quando", "nav_font": "Fonte",
        "nav_keyboard": "Teclado", "nav_settings": "Configurações", "nav_about": "Sobre",
        "clock_sub": "O que o seu teclado mostra quando você não está.",
        "live_preview": "Prévia ao vivo", "show_keyboard": "Mostrar no teclado",
        "screen_secs": "Cada tela dura", "transition": "Transição", "tr_fade": "Esmaecer", "tr_slide": "Deslizar",
        "tr_wipe": "Varredura", "tr_dissolve": "Dissolver", "tr_none": "Nenhuma",
        "scroll_text": "Texto rolante", "scroll_speed": "Velocidade", "scroll_smooth": "Rolagem suave",
        "scroll_smooth_desc": "Desligado: o texto anda tecla por tecla, mais nítido nas teclas",
        "text_time": "Hora", "text_time_date": "Hora e data", "text_date": "Data", "text_seconds": "Hora com segundos",
        "text_custom": "Seu próprio texto…", "text_dialog": "Texto rolante",
        "text_prompt": "Texto para rolar no teclado:",
        "text_hint": "Valores ao vivo: {time} {hours} {minutes} {seconds} {weekday} {date} {day} {month} {year}",
        "ok": "OK", "cancel": "Cancelar",
        "formats": "Formatos", "hour12": "Formato de 12 horas", "leading_zero": "Zero à esquerda",
        "leading_zero_desc": "09:05 em vez de 9:05", "seconds": "Segundos", "sec_block": "Bloco",
        "sec_bar": "Barra", "sec_numpad": "Teclado num.", "sec_beat": "Pulso", "sec_off": "Nenhum",
        "look_sub": "Cores, fundo e efeitos.", "themes": "Temas",
        "theme_neon": "Neon", "theme_matrix": "Matrix", "theme_sunset": "Pôr do sol", "theme_ocean": "Oceano",
        "theme_white": "Branco", "theme_rainbow": "Arco-íris", "theme_daylight": "Cores do dia",
        "theme_night_red": "Vermelho noturno",
        "colors": "Cores", "style": "Estilo", "style_solid": "Uma cor por parte", "style_gradient": "Degradê",
        "style_flow": "Degradê em movimento", "style_rainbow": "Arco-íris", "style_daytime": "Cores do dia",
        "style_digits": "Uma cor por dígito",
        "style_rainbow_desc": "Todas as cores, deslizando devagar pelas teclas.",
        "style_daytime_desc": "Laranja de manhã, ciano durante o dia, roxo à noite: a cor acompanha a hora.",
        "role_hours": "Horas", "role_minutes": "Minutos", "role_date": "Data", "role_seconds": "Segundos",
        "role_text": "Texto", "digit_left": "Dígito esquerdo", "digit_right": "Dígito direito",
        "color_hue": "Matiz", "color_sat": "Saturação",
        "background": "Fundo", "bg_off": "Apagado", "bg_dim": "Atenuado", "bg_gradient": "Degradê",
        "bg_breathe": "Respiração", "bg_twinkle": "Estrelas", "bg_level": "Brilho do fundo",
        "bg_gradient_desc": "As outras teclas pegam as cores do degradê acima, atenuadas.",
        "effects": "Efeitos", "chime": "Badalada", "chime_off": "Nenhuma", "chime_hour": "A cada hora",
        "chime_half": "A cada meia hora",
        "when_sub": "Quando o relógio assume a iluminação do seu teclado.", "show_clock": "Mostrar o relógio",
        "when_idle": "Quando saio", "when_always": "Sempre", "when_manual": "Pelo atalho", "after": "Após",
        "on_lock": "Assim que o PC for bloqueado", "on_lock_desc": "Win+L mostra na hora",
        "hide_fullscreen": "Não durante jogos e vídeos em tela cheia",
        "hide_fullscreen_desc": "A iluminação deles continua",
        "hotkey": "Atalho", "hotkey_desc": "Mostra ou oculta o relógio de qualquer lugar", "hotkey_none": "Nenhum",
        "off_after": "Depois, apagar as teclas após", "off_after_desc": "O teclado fica apagado até você voltar",
        "never": "Nunca", "night": "Noite", "night_hours": "Horário noturno", "night_from": "Das", "night_to": "às",
        "at_night": "À noite", "night_dim": "Atenuado", "night_red": "Em vermelho", "night_dark": "Apagado",
        "night_brightness": "Brilho à noite",
        "font_sub": "Desenhe cada dígito tecla por tecla, à esquerda e à direita: as teclas de função não ficam "
                    "iguais acima de cada um.",
        "font_use": "Usar meus dígitos", "font_use_desc": "Desligado: os dígitos originais", "font_digit": "Dígito",
        "font_left": "Esquerda", "font_right": "Direita",
        "font_hint": "Clique em uma tecla para acendê-la ou apagá-la. Cada lado tem suas próprias teclas.",
        "font_reset": "Redefinir dígito", "font_copy": "Copiar para o outro lado", "font_reset_all": "Redefinir tudo",
        "keyboard_sub": "O teclado que o Keyboard Clock controla.", "kb_ghub": "Logitech G (G HUB)",
        "kb_ok": "Pronto", "kb_missing": "G HUB não encontrado",
        "kb_help": "No G HUB, abra as Configurações e ative “Permitir que jogos e aplicativos controlem minha "
                   "iluminação”.",
        "kb_layout": "Layout", "model_auto": "Automático",
        "model_tkl-iso": "Sem teclado numérico, ISO (Europa)", "model_tkl-ansi": "Sem teclado numérico, ANSI (EUA)",
        "model_full-iso": "Completo, ISO (Europa)", "model_full-ansi": "Completo, ANSI (EUA)",
        "kb_test": "Testar meu teclado", "kb_test_desc": "Mostra de 0 a 9 dos dois lados",
        "kb_test_button": "Testar", "kb_more": "Outras marcas",
        "kb_more_desc": "Teclados com a Iluminação dinâmica do Windows e com OpenRGB chegam em breve.",
        "settings_sub": "Inicialização, atualizações e idioma.",
        "settings_start_desc": "Roda em segundo plano, ao lado do relógio", "settings_updates": "Atualizações",
        "settings_new": "A versão {version} está disponível", "settings_check_now": "Verificar",
        "settings_check_desc": "Uma vez por dia, no GitHub", "settings_lang": "Idioma",
        "settings_lang_label": "Idioma do app", "lang_auto": "Idioma do Windows", "settings_help": "Ajuda",
        "settings_open": "Abrir", "settings_log_desc": "O que o Keyboard Clock fez, para relatar um problema",
        "about_version": "Versão {version}",
        "about_tagline": "Seu teclado mostra a hora quando você não está, em grandes dígitos desenhados nas teclas. "
                         "Gratuito e de código aberto.",
        "about_site": "Site", "about_source": "Código-fonte", "about_issue": "Relatar um problema",
        "about_license": "Licença MIT. Logitech e G HUB são marcas da Logitech; o Keyboard Clock não é afiliado à "
                         "Logitech.",
        "secs_fmt": "{n} s", "mins_fmt": "{n} min", "hours_fmt": "{n} h",
    },
}
_lang = {"code": "en"}


def set_lang(code):
    _lang["code"] = code if code in STRINGS else "en"


def tr(key, **kw):
    text = STRINGS[_lang["code"]].get(key) or STRINGS["en"][key]
    return text.format(**kw) if kw else text


def tr_secs(n):
    n = int(n)
    if n < 60:
        return tr("secs_fmt", n=n)
    if n < 3600 or n % 3600:
        return tr("mins_fmt", n=round(n / 60, 1) if n % 60 else n // 60)
    return tr("hours_fmt", n=n // 3600)


# ---- Windows integration: icon, autostart, Start menu, install, uninstall
START_MENU_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs",
                              f"{APP}.lnk")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTHOR, AUTHOR_URL = "Ilyomix", "https://github.com/Ilyomix"
SITE_URL = "https://ilyomix.github.io/keyboard-clock/"
ICON_COLORS = ((255, 89, 0), (0, 204, 255))


def icon_pixels(size, paused=False):
    """BGRA pixels of the icon: a 3x3 block of keys filling up like the seconds counter, orange to cyan."""
    px = bytearray(size * size * 4)
    ss = 4
    margin, gap = size * 0.06, size * 0.07
    cell = (size - 2 * margin - 2 * gap) / 3
    radius = cell * 0.22
    cells = []
    for i in range(9):
        r, c = divmod(i, 3)
        x0, y0 = margin + c * (cell + gap), margin + r * (cell + gap)
        if i < 6:
            t = i / 5
            col = tuple(ICON_COLORS[0][k] + (ICON_COLORS[1][k] - ICON_COLORS[0][k]) * t for k in range(3))
            alpha = 1.0
        elif i == 6:
            col, alpha = ICON_COLORS[1], 0.55
        else:
            col, alpha = (120, 126, 140), 0.55
        if paused:
            lum = 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2]
            col, alpha = (lum, lum, lum), alpha * 0.7
        cells.append((x0, y0, col, alpha))

    def inside(x, y, x0, y0):
        dx = max(x0 + radius - x, 0.0, x - (x0 + cell - radius))
        dy = max(y0 + radius - y, 0.0, y - (y0 + cell - radius))
        return dx * dx + dy * dy <= radius * radius

    for y in range(size):
        for x in range(size):
            for x0, y0, col, alpha in cells:
                if x0 - 1 <= x <= x0 + cell + 1 and y0 - 1 <= y <= y0 + cell + 1:
                    hits = sum(inside(x + (i + 0.5) / ss, y + (j + 0.5) / ss, x0, y0) for i in range(ss) for j in range(ss))
                    if hits:
                        a = alpha * hits / (ss * ss)
                        i_ = (y * size + x) * 4
                        px[i_:i_ + 4] = bytes((int(col[2]), int(col[1]), int(col[0]), int(255 * a)))
                    break
    return px


def write_ico(path, paused=False, sizes=(16, 20, 24, 32, 48, 64, 256)):
    images = []
    for s in sizes:
        rows = icon_pixels(s, paused)
        xor = b"".join(bytes(rows[y * s * 4:(y + 1) * s * 4]) for y in reversed(range(s)))
        andmask = bytes(((s + 31) // 32) * 4 * s)
        bih = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0, len(xor) + len(andmask), 0, 0, 0, 0)
        images.append((s, bih + xor + andmask))
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, data in images:
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(out + b"".join(d for _, d in images))


def ensure_icons():
    os.makedirs(DATA_DIR, exist_ok=True)
    paths = (os.path.join(DATA_DIR, f"keyboard-clock-{__version__}.ico"),
             os.path.join(DATA_DIR, f"keyboard-clock-{__version__}-paused.ico"))
    for p, paused in zip(paths, (False, True)):
        if not os.path.exists(p):
            write_ico(p, paused)
    return paths


def launch_command(extra=()):
    """Command line that starts Keyboard Clock in the background (icon next to the clock, no console)."""
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
        for gui in ("KeyboardClock.exe", "KeyboardClockPortable.exe"):
            if os.path.exists(os.path.join(here, gui)):
                return [os.path.join(here, gui), "--background", *extra]
        return [sys.executable, "--background", *extra]
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return [pyw if os.path.exists(pyw) else sys.executable, os.path.abspath(__file__), "--background", *extra]


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_ID)
            return True
    except OSError:
        return False


def set_autostart(enable, argv=()):
    import subprocess
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ,
                              subprocess.list2cmdline(launch_command(["--from-autostart", *argv])))
        else:
            try:
                winreg.DeleteValue(k, APP_ID)
            except FileNotFoundError:
                pass


def make_start_menu_shortcut(argv=()):
    import subprocess
    icon = ensure_icons()[0]
    cmd = launch_command(argv)
    cmd = [c for c in cmd if c != "--background"]       # from the Start menu: the window opens
    q = lambda s: "'" + s.replace("'", "''") + "'"
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({q(START_MENU_LNK)});"
              f"$s.TargetPath={q(cmd[0])};$s.Arguments={q(subprocess.list2cmdline(cmd[1:]))};"
              f"$s.IconLocation={q(icon)};$s.Description={q(APP + ' - the time on your RGB keyboard')};$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True,
                   creationflags=0x08000000, capture_output=True)


def cmd_install(argv):
    set_autostart(True, argv)
    make_start_menu_shortcut(argv)
    print(f"{APP} is installed: it starts with Windows (icon next to the clock) and is in the Start menu.")
    print("To remove it: keyboard_clock.py --uninstall")


def cmd_uninstall():
    import shutil
    if request_stop():
        for _ in range(30):
            h = k32.OpenEventW(0x00100000, False, STOP_EVENT)     # SYNCHRONIZE
            if not h:
                break
            k32.CloseHandle(h)
            time.sleep(0.1)
    set_autostart(False)
    try:
        os.remove(START_MENU_LNK)
    except FileNotFoundError:
        pass
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    print(f"{APP} was stopped and removed from startup, the Start menu and %LOCALAPPDATA%\\{APP_ID}.")


# ---- fonts and drawing helpers
_ui = {"face": None, "fonts": [], "gdip": None}


def ui_font_face():
    """The embedded Inter (private to this process), or Segoe UI."""
    if _ui["face"] is None:
        _ui["face"] = "Segoe UI"
        try:
            import base64
            for parts in INTER_FONTS:
                data = zlib.decompress(base64.b64decode("".join(parts)))
                buf = ctypes.create_string_buffer(data, len(data))
                n = wt.DWORD()
                if gdi32.AddFontMemResourceEx(buf, len(data), None, byref(n)):
                    _ui["fonts"].append(buf)
                    _ui["face"] = "Glowback Inter"          # the family name inside the embedded font
        except Exception:
            pass
    return _ui["face"]


def icon_font_face():
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    return "Segoe Fluent Icons" if os.path.exists(os.path.join(fonts, "SegoeIcons.ttf")) else "Segoe MDL2 Assets"


def _gdip_start():
    if _ui["gdip"] is None:
        token, inp = ctypes.c_size_t(), GdiplusStartupInput(1, None, False, False)
        _ui["gdip"] = gdiplus.GdiplusStartup(byref(token), byref(inp), None) == 0
    return _ui["gdip"]


def _cref(rgb):  # 0xRRGGBB -> COLORREF
    return ((rgb >> 16) & 0xFF) | (rgb & 0xFF00) | ((rgb & 0xFF) << 16)


def cint(c):
    """'#rrggbb' or (r, g, b) -> 0xRRGGBB."""
    r, g, b = hex_color(c) if isinstance(c, str) else c
    return (int(r) << 16) | (int(g) << 8) | int(b)


def color_hsv(c):
    r, g, b = ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s, v


def hsv_color(h, s, v=1.0):
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360, s, v)
    return (round(r * 255) << 16) | (round(g * 255) << 8) | round(b * 255)


SWATCHES = (0xFF1A1A, 0xFF5900, 0xFFB000, 0xFFE600, 0x00FF41, 0x00CCFF, 0x0050FF, 0x8B2BFF, 0xFF2E9A, 0xFFFFFF)


class MenuPainter:
    """Draws the tray menu: header with live status, icons, radio buttons, switches, sections."""
    BG, HOVER, TEXT, MUTED, ICON = 0x141519, 0x23252E, 0xECEEF3, 0x8C91A1, 0xC5C9D4
    ACCENT, LINE, OFF, RING, LABEL = 0x8B6CFF, 0x2B2D38, 0x3A3D49, 0x5B5F6E, 0x9D86FF
    GREEN, AMBER = 0x3DDC97, 0xF5B83D
    HEIGHTS = {"header": 64, "sep": 13, "label": 30}
    ICONS = {"light": "", "power": "", "sync": "", "monitor": "", "palette": "",
             "sun": "", "person": "", "star": "", "doc": "", "close": "",
             "link": ""}
    ICONS.update(dismiss="", quit="", check="", warning="", clock="")
    ICONS.update(home="")
    ICONS.update(phone="", qr="")  # CellPhone, QRCode
    ICONS.update(filter="", settings="", info="", chev_down="", chev_right="",
                 delete="", globe="", code="", bug="", window="", add="",
                 lang="", mic="", apps="", pause="", search="")

    ICONS.update(moon="", drop="", gradient="", music="", pulse="",
                 spectrum="", wave="", layers="", minus="", chev_left="",
                 volume="", sparkle="", bulb="", flow="", arrow="")

    def __init__(self, scale, icon):
        self.k, self.icon = scale, icon
        face = ui_font_face()
        mk = lambda px, weight, f=face: gdi32.CreateFontW(-round(px * scale), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, f)
        self.f_text, self.f_title, self.f_small, self.f_label = mk(13.5, 400), mk(15, 600), mk(12, 400), mk(11, 600)
        self.f_icon, self.f_link = mk(16, 400, icon_font_face()), mk(12, 400, icon_font_face())
        self.f_chev = mk(17, 400)
        self.f_close = mk(10, 400, icon_font_face())
        self.bg_brush = gdi32.CreateSolidBrush(_cref(self.BG))
        self.line_brush = gdi32.CreateSolidBrush(_cref(self.LINE))
        self.mdc = gdi32.CreateCompatibleDC(None)  # for measuring text
        self.gdip = _gdip_start()
        self.styled = set()

    def close(self):
        for h in (self.f_text, self.f_title, self.f_small, self.f_label, self.f_icon, self.f_link, self.f_chev,
                  self.f_close, self.bg_brush, self.line_brush):
            gdi32.DeleteObject(h)
        gdi32.DeleteDC(self.mdc)

    def px(self, v):
        return round(v * self.k)

    def text_width(self, text, font):
        gdi32.SelectObject(self.mdc, font)
        size = wt.SIZE()
        gdi32.GetTextExtentPoint32W(self.mdc, text, len(text), byref(size))
        return size.cx

    def measure(self, mis, it):
        p, kind = self.px, it["kind"]
        mis.itemHeight = p(self.HEIGHTS.get(kind, 34))
        if kind == "sep":
            w = 0
        elif kind == "header":  # icon, name + version over the status, close button
            title = self.text_width(APP, self.f_title) + p(7) + self.text_width(f"v{__version__}", self.f_small)
            w = p(56) + max(title, p(14) + self.text_width(it["status"], self.f_small)) + p(16 + 32 + 8)
        elif kind == "label":
            w = p(18 + 16) + self.text_width(it["text"].upper(), self.f_label)
        else:
            left = p(46) if it.get("icon") or "swatch" in it or "stops" in it else p(18)
            w = left + self.text_width(it["text"], self.f_text) + self.right_space(it) + p(8)
        mis.itemWidth = max(w, p(it.get("min", 232)))

    def right_space(self, it):
        """Room kept on the right of the label for the item's control (switch, radio, value, link)."""
        p, kind = self.px, it["kind"]
        if kind == "toggle":
            return p(16 + 34 + 14)
        if kind == "radio":
            return p(16 + 16 + 14)
        if kind == "submenu":
            return p(16 + 16 + 12) + self.text_width(it.get("value", ""), self.f_small)
        if kind == "segments":
            return p(16 + 12) + len(it["values"]) * p(it.get("seg_w", 44)) + (len(it["values"]) - 1) * p(3)
        if it.get("statuses"):  # room for the loader, or the widest result with its glyph
            return p(16 + 12) + max([p(16)] + [p(17) + self.text_width(t, self.f_small) for t in it["statuses"]])
        return p(16 + 14 + 12) if it.get("link") else p(16)

    def close_rect(self, l, t, r, b):
        """The close button, on the right of the header."""
        size = self.px(32)
        x1, y0 = r - self.px(8), t + (b - t - size) // 2
        return x1 - size, y0, x1, y0 + size

    def segment_rects(self, it, l, t, r, b):
        """(x0, y0, x1, y1) of each choice of a "segments" item, right-aligned in the row."""
        p, n = self.px, len(it["values"])
        w, gap = p(it.get("seg_w", 44)), p(3)
        x = r - p(16) - n * w - (n - 1) * gap
        return [(x + i * (w + gap), t + p(6), x + i * (w + gap) + w, b - p(6)) for i in range(n)]

    def style_window(self, hwnd):
        """Windows 11: dark border and rounded corners on the menu window."""
        if hwnd and hwnd not in self.styled:
            self.styled.add(hwnd)
            border, corner = wt.DWORD(_cref(0x2C2E38)), wt.DWORD(2)
            dwmapi.DwmSetWindowAttribute(hwnd, 34, byref(border), 4)  # DWMWA_BORDER_COLOR
            dwmapi.DwmSetWindowAttribute(hwnd, 33, byref(corner), 4)  # DWMWA_WINDOW_CORNER_PREFERENCE

    def _text(self, hdc, text, font, color, l, t, r, b, flags=0):
        gdi32.SelectObject(hdc, font)
        gdi32.SetTextColor(hdc, _cref(color))
        rc = wt.RECT(int(l), int(t), int(r), int(b))
        user32.DrawTextW(hdc, text, -1, byref(rc), 0x20 | 0x04 | 0x800 | flags)  # SINGLELINE|VCENTER|NOPREFIX

    def _shapes(self, hdc, shapes):
        """Antialiased shapes with GDI+: ("round", color, x, y, w, h, radius) or ("circle", color, x, y, d)."""
        if not self.gdip or not shapes:
            return
        g = VP()
        if gdiplus.GdipCreateFromHDC(hdc, byref(g)):
            return
        gdiplus.GdipSetSmoothingMode(g, 4)
        gdiplus.GdipSetPixelOffsetMode(g, 4)
        for shape in shapes:
            if shape[0] == "hgrad":  # ("hgrad", colors, x, y, w, h, radius): a gradient (look menus)
                gdip_hgrad(g, *shape[1:])
                continue
            if shape[0] == "arc":  # ("arc", color, x, y, d, start, sweep, width): the update loader
                _, color, x, y, d, start, sweep, width = shape
                pen = VP()
                gdiplus.GdipCreatePen1(0xFF000000 | color, width, 2, byref(pen))  # UnitPixel
                gdiplus.GdipSetPenStartCap(pen, 2)  # LineCapRound
                gdiplus.GdipSetPenEndCap(pen, 2)
                gdiplus.GdipDrawArc(g, pen, x, y, d, d, start, sweep)
                gdiplus.GdipDeletePen(pen)
                continue
            brush = VP()
            gdiplus.GdipCreateSolidFill(0xFF000000 | shape[1], byref(brush))
            if shape[0] == "circle":
                _, _, x, y, d = shape
                gdiplus.GdipFillEllipse(g, brush, x, y, d, d)
            else:
                _, _, x, y, w, h, r = shape
                d = max(1.0, min(2 * r, w, h))
                path = VP()
                gdiplus.GdipCreatePath(0, byref(path))
                gdiplus.GdipAddPathArc(path, x, y, d, d, 180, 90)
                gdiplus.GdipAddPathArc(path, x + w - d, y, d, d, 270, 90)
                gdiplus.GdipAddPathArc(path, x + w - d, y + h - d, d, d, 0, 90)
                gdiplus.GdipAddPathArc(path, x, y + h - d, d, d, 90, 90)
                gdiplus.GdipClosePathFigure(path)
                gdiplus.GdipFillPath(g, brush, path)
                gdiplus.GdipDeletePath(path)
            gdiplus.GdipDeleteBrush(brush)
        gdiplus.GdipDeleteGraphics(g)

    def draw(self, dis, it):
        hdc, rc, p = dis.hDC, dis.rcItem, self.px
        kind = it["kind"]
        l, t, r, b = rc.left, rc.top, rc.right, rc.bottom
        h = b - t
        user32.FillRect(hdc, byref(rc), self.bg_brush)
        gdi32.SetBkMode(hdc, 1)  # transparent
        hovered = bool(dis.itemState & 0x1) and kind not in ("header", "sep", "label", "segments")
        under = self.HOVER if hovered else self.BG
        shapes = []
        if hovered:
            shapes.append(("round", self.HOVER, l + p(6), t + p(2), r - l - p(12), h - p(4), p(7)))
        if kind == "sep":
            line = wt.RECT(l + p(10), t + h // 2, r - p(10), t + h // 2 + max(1, p(1)))
            user32.FillRect(hdc, byref(line), self.line_brush)
        elif kind == "header":
            d = p(8)
            color = {"on": self.GREEN, "off": self.OFF + 0x202020, "none": self.AMBER}[it["state"]]
            shapes.append(("circle", color, l + p(56), t + h * 0.68 - d / 2, d))
            if it.get("hover_seg") == "close":
                x0, y0, x1, y1 = self.close_rect(l, t, r, b)
                shapes.append(("round", self.HOVER, x0, y0, x1 - x0, y1 - y0, p(6)))
        elif kind == "action" and it.get("busy"):  # loader: an accent arc running around a faint ring
            d, width = p(14), max(1.5, self.k * 1.8)
            x_, y_, now = r - p(16) - d, t + (h - d) / 2, time.monotonic()
            sweep = 40 + 230 * (0.5 - 0.5 * math.cos(now * 2 * math.pi / 1.6))
            shapes += [("arc", self.LINE, x_, y_, d, 0, 360, width),
                       ("arc", self.ACCENT, x_, y_, d, (now * 320) % 360, sweep, width)]
        elif kind == "toggle":
            w_, h_ = p(34), p(19)
            x_, y_ = r - p(16) - w_, t + (h - h_) / 2
            knob = h_ - p(6)
            shapes.append(("round", self.ACCENT if it["on"] else self.OFF, x_, y_, w_, h_, h_ / 2))
            kx = x_ + w_ - knob - p(3) if it["on"] else x_ + p(3)
            shapes.append(("circle", 0xFFFFFF if it["on"] else 0xC8CBD4, kx, y_ + p(3), knob))
        elif kind == "segments":
            segs = self.segment_rects(it, l, t, r, b)
            shapes.append(("round", 0x1E2028, segs[0][0] - p(2), segs[0][1] - p(2), segs[-1][2] - segs[0][0] + p(4),
                           segs[0][3] - segs[0][1] + p(4), p(8)))
            for i, (x0, y0, x1, y1) in enumerate(segs):
                if it["values"][i] == it["value"]:
                    shapes.append(("round", self.ACCENT, x0, y0, x1 - x0, y1 - y0, p(6)))
                elif it.get("hover_seg") == i:
                    shapes.append(("round", self.HOVER, x0, y0, x1 - x0, y1 - y0, p(6)))
        if "swatch" in it:  # a color, before the text
            d = p(16)
            shapes.append(("circle", it["swatch"], l + p(18), t + (h - d) / 2, d))
        elif "stops" in it:  # a gradient
            shapes.append(("hgrad", it["stops"], l + p(14), t + (h - p(12)) / 2, p(24), p(12), p(6)))
        if kind == "radio":
            d = p(16)
            x_, y_ = r - p(16) - d, t + (h - d) / 2
            if it.get("checked"):
                shapes += [("circle", self.ACCENT, x_, y_, d), ("circle", 0xFFFFFF, x_ + d / 2 - p(3), y_ + d / 2 - p(3), p(6))]
            else:
                ring = max(1.5, p(1.5))
                shapes += [("circle", self.RING, x_, y_, d), ("circle", under, x_ + ring, y_ + ring, d - 2 * ring)]
        self._shapes(hdc, shapes)

        if kind == "header":
            size = p(28)
            user32.DrawIconEx(hdc, l + p(16), t + (h - size) // 2, self.icon, size, size, 0, None, 3)
            x, (cx0, cy0, cx1, cy1) = l + p(56), self.close_rect(l, t, r, b)
            self._text(hdc, APP, self.f_title, self.TEXT, x, t + p(8), cx0, t + h * 0.46)
            vx = x + self.text_width(APP, self.f_title) + p(7)
            self._text(hdc, f"v{__version__}", self.f_small, self.MUTED, vx, t + p(9), cx0, t + h * 0.46 + p(1))
            self._text(hdc, it["status"], self.f_small, self.MUTED, x + p(14), t + h * 0.46, cx0, b - p(6))
            self._text(hdc, self.ICONS["dismiss"], self.f_close, self.TEXT if it.get("hover_seg") == "close" else self.ICON,
                       cx0, cy0, cx1, cy1, 0x1)
        elif kind == "label":
            self._text(hdc, it["text"].upper(), self.f_label, self.LABEL, l + p(18), t + p(8), r, b)
        elif kind != "sep":
            x = l + p(46) if "swatch" in it or "stops" in it else l + p(18)
            if it.get("icon"):
                color = self.ACCENT if it.get("accent") else self.ICON
                self._text(hdc, self.ICONS[it["icon"]], self.f_icon, color, l + p(10), t, l + p(42), b, 0x1)
                x = l + p(46)
            self._text(hdc, it["text"], self.f_text, self.ACCENT if it.get("highlight") else self.TEXT, x, t,
                       r - self.right_space(it), b, 0x8000)  # DT_END_ELLIPSIS as a last resort
            right = r - p(16)
            if kind == "submenu":
                self._text(hdc, "›", self.f_chev, self.MUTED, l, t - p(1), right, b, 0x2)
                self._text(hdc, it.get("value", ""), self.f_small, self.MUTED, l, t, right - p(16), b, 0x2)
                gdi32.ExcludeClipRect(hdc, r - p(28), t, r, b)  # hide the system's own submenu arrow
            elif kind == "action" and it.get("link"):
                self._text(hdc, self.ICONS["link"], self.f_link, self.MUTED, l, t, right, b, 0x2)
            elif kind == "action" and it.get("status") and not it.get("busy"):
                text, color, glyph = it["status"]
                self._text(hdc, text, self.f_small, color, l, t, right, b, 0x2)
                if glyph:
                    gx = right - self.text_width(text, self.f_small) - p(5)
                    self._text(hdc, self.ICONS[glyph], self.f_link, color, l, t, gx, b, 0x2)
            elif kind == "segments":
                for i, (x0, y0, x1, y1) in enumerate(self.segment_rects(it, l, t, r, b)):
                    on = it["values"][i] == it["value"]
                    color = 0xFFFFFF if on else (self.TEXT if it.get("hover_seg") == i else self.MUTED)
                    if it.get("glyphs"):
                        self._text(hdc, it["glyphs"][i], self.f_icon, color, x0, y0, x1, y1, 0x1)
                    else:
                        self._text(hdc, f"{it['values'][i]}%", self.f_small, color, x0, y0, x1, y1, 0x1)
MenuPainter.ICONS.update(calendar="\uE787", keyboard="\uE765", font="\uE8D2", edit="\uE70F", timer="\uE916")


def taskbar():
    """The taskbar that holds the notification area: (edge, rect), edge 0 left, 1 top, 2 right, 3 bottom."""
    abd = APPBARDATA()
    abd.cbSize = sizeof(abd)
    if shell32.SHAppBarMessage(5, byref(abd)):  # ABM_GETTASKBARPOS
        return abd.uEdge, abd.rc
    return None


def dock_flyout(pt, w, h, gap, work, screen, bar):
    """Top-left corner of the w x h panel opened from the tray icon clicked at pt: against the taskbar, like
    Windows' own flyouts. (Placed from the cursor, it was left floating mid-screen whenever the icon sat in the
    hidden-icons overflow, which closes as soon as the panel opens.)"""
    def clamp(v, lo, hi):
        return max(lo, min(v, hi))
    edge, rc = bar or (3, wt.RECT(work.left, work.bottom, work.right, work.bottom))
    if edge in (1, 3):  # taskbar on top or at the bottom: centred on the icon, along the taskbar
        x = clamp(pt.x - w // 2, work.left + gap, work.right - w - gap)
        y = max(rc.bottom, work.top) + gap if edge == 1 else min(rc.top, work.bottom) - h - gap
    else:  # on the left or the right (Windows 10)
        y = clamp(pt.y - h // 2, work.top + gap, work.bottom - h - gap)
        x = max(rc.right, work.left) + gap if edge == 0 else min(rc.left, work.right) - w - gap
    return clamp(x, screen.left, screen.right - w), clamp(y, screen.top, screen.bottom - h)


def logitech_dll():
    bits = "x64" if struct.calcsize("P") == 8 else "x86"
    for c in (rf"C:\Program Files\LGHUB\sdks\sdk_legacy_led_{bits}.dll", rf"C:\Program Files\LGHUB\sdk_legacy_led_{bits}.dll"):
        if os.path.isfile(c):
            return c
    return None


class Store:
    """The settings the app edits: each change is checked, saved and handed to the clock at once."""

    def __init__(self, clock):
        self.clock = clock

    @property
    def s(self):
        return self.clock.settings

    def get(self, path):
        d = self.s
        for k in path:
            d = d[k]
        return d

    def set(self, path, value, save=True):
        s = json.loads(json.dumps(self.s))
        d = s
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value
        self.replace(s, save)

    def replace(self, s, save=True):
        s = clean_settings(s)
        if save:
            try:
                save_settings(s, self.clock.path)
            except OSError as e:
                log(f"Settings not saved: {e}")
        self.clock.apply(s)
        self.clock.notify()


class Tray:
    """The icon next to the clock and its panel."""
    WM_TRAY, WM_CLOSE_APP, WM_UPDATE, WM_CHECKED, WM_OPEN_APP, WM_SYNC = 0x8001, 0x8002, 0x8003, 0x8004, 0x8007, 0x8008
    MODES = ("time", "time_date", "scroll", "mixed")

    def __init__(self, clock, stop, argv):
        self.clock, self.stop, self.argv = clock, stop, argv
        self.store = Store(clock)
        self.worker, self.app = None, None
        self.started, self.restarting = time.monotonic(), False
        on, off = ensure_icons()
        self.icon_path = on
        self.painter, self.balloon = None, None
        cx, cy = user32.GetSystemMetrics(49), user32.GetSystemMetrics(50)
        self.icons = (user32.LoadImageW(None, on, 1, cx, cy, 0x10), user32.LoadImageW(None, off, 1, cx, cy, 0x10))
        self._proc_ref = WNDPROC(self._proc)
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = sizeof(wc), self._proc_ref, hinst, "KeyboardClockTray"
        user32.RegisterClassExW(byref(wc))
        self.flyout, self.flyout_closed, self.autostart, self.fly_place = None, 0.0, False, None
        self.checking, self.check_result, self.check_time = False, None, 0.0
        self.hover = self.hover_seg = None
        self._fly_ref = WNDPROC(self._fly_proc)
        fc = WNDCLASSEXW()
        fc.cbSize, fc.lpfnWndProc, fc.hInstance, fc.lpszClassName = sizeof(fc), self._fly_ref, hinst, "KeyboardClockFlyout"
        fc.style = 0x00020000                                          # CS_DROPSHADOW
        fc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
        user32.RegisterClassExW(byref(fc))
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.hwnd = user32.CreateWindowExW(0, "KeyboardClockTray", APP, 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        shell32.Shell_NotifyIconW(0, byref(self._nid()))

    # ---- status
    def status(self):
        """(text, dot) for the panel's header and the window's sidebar: dot on, off or none (amber)."""
        c, s = self.clock, self.clock.settings
        st = c.status
        if st == "showing":
            return tr("status_showing"), "on"
        if st == "off":
            return tr("status_off"), "off"
        if st == "paused":
            until = dt.datetime.now() + dt.timedelta(seconds=max(0.0, c.paused_until - time.monotonic()))
            return tr("status_paused", time=until.strftime("%H:%M")), "none"
        if st in ("hidden_app", "no_keyboard"):
            return tr("status_" + st), "none"
        when = s["show"]["when"]
        if when == "always":
            return tr("status_always"), "on"
        if when == "manual":
            hk = s["show"]["hotkey"]
            return (tr("status_manual", hotkey=hk) if parse_hotkey(hk) else tr("status_manual_none")), "on"
        return tr("status_waiting", delay=tr_secs(s["show"]["delay"])), "on"

    def _nid(self, info=None):
        n = NOTIFYICONDATAW()
        n.cbSize, n.hWnd, n.uID, n.uCallbackMessage = sizeof(n), self.hwnd, 1, self.WM_TRAY
        n.uFlags = 0x1 | 0x2 | 0x4
        c = self.clock
        n.hIcon = self.icons[0 if c.settings["enabled"] and not c.paused() else 1]
        n.szTip = f"{APP}\n{self.status()[0]}"[:127]
        if info:
            n.uFlags |= 0x10
            n.szInfoTitle, n.szInfo = info
        return n

    def refresh(self, info=None):
        shell32.Shell_NotifyIconW(1, byref(self._nid(info)))

    # ---- updates
    def start_update(self):
        c = self.clock
        if not c.update_info or getattr(self, "updating", False):
            return
        self.updating, self.balloon = True, None
        self.refresh((APP, tr("update_downloading", version=c.new_version)))

        def work():
            try:
                apply_update(c.update_info)
                log(f"Updating to {c.new_version}")
                self.refresh((APP, tr("update_installing")))
                time.sleep(1.5)
                k32.SetEvent(self.stop.h)
            except Exception as e:
                log(f"Update failed: {e!r}")
                self.updating = False
                self.refresh((APP, tr("update_failed", error=str(e) or e.__class__.__name__)))
                os.startfile(update_url(c))

        threading.Thread(target=work, name="keyboard-clock-updating", daemon=True).start()

    def check_now(self):
        if self.checking:
            return
        self.checking, self.check_result = True, None
        if self.flyout:
            user32.SetTimer(self.flyout, 1, 33, None)
        c, started = self.clock, time.monotonic()

        def work():
            try:
                info = latest_release()
                tag = info["version"]
                if tag and _version_tuple(tag) > _version_tuple(__version__):
                    c.new_version, c.update_page, c.update_info = tag, info["page"], info
                    log(f"Update available: {tag}")
                    result = "found"
                else:
                    result = "latest"
            except Exception as e:
                log(f"Update check failed ({e.__class__.__name__}: {e})")
                result = "error"
            time.sleep(max(0.0, 0.8 - (time.monotonic() - started)))
            self.check_result = result
            user32.PostMessageW(self.hwnd, self.WM_CHECKED, 0, 0)

        threading.Thread(target=work, name="keyboard-clock-check", daemon=True).start()

    def _check_status(self):
        if self.checking or not self.check_result or time.monotonic() - self.check_time > 600:
            return None
        if self.check_result == "found" and self.clock.new_version:
            return f"v{self.clock.new_version}", MenuPainter.ACCENT, None
        if self.check_result == "latest":
            return tr("up_to_date"), MenuPainter.GREEN, "check"
        return tr("check_failed"), MenuPainter.AMBER, "warning"

    # ---- window and loop
    def close_from_thread(self):
        user32.PostMessageW(self.hwnd, self.WM_CLOSE_APP, 0, 0)

    def loop(self):
        msg = wt.MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            dialog = InputDialog.current
            if dialog and dialog.hwnd and user32.IsDialogMessageW(dialog.hwnd, byref(msg)):
                continue
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

    def open_app(self, page=None):
        if self.flyout and user32.IsWindow(self.flyout):
            user32.PostMessageW(self.flyout, 0x0010, 0, 0)
        try:
            if not self.app:
                self.app = AppWindow(self)
            self.app.open(page)
        except Exception as e:
            log(f"App window: {e!r}")
        if self.app and self.app.hwnd:
            return
        if time.monotonic() - self.started > 60 and not self.restarting:
            import subprocess
            self.restarting = True
            log("The window could not open: restarting.")
            subprocess.Popen(launch_command(self.argv), creationflags=0x00000008 | 0x00000200, close_fds=True)

    def app_closed(self):
        if not load_settings().get("told_background") and not getattr(self, "told", False):
            self.told = True
            self.refresh((APP, tr("app_background")))

    def _changed(self):
        if self.flyout and self.painter:
            user32.InvalidateRect(self.flyout, None, False)
        if self.app:
            self.app.invalidate()

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            return self._on(hwnd, msg, wparam, lparam)
        except Exception as e:
            log(f"Tray: {e!r}")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_TRAY:
            event = lparam & 0xFFFF
            if event in (0x0202, 0x0205, 0x007B):
                self._menu()
            elif event == 0x0203:
                self.open_app()
            elif event == 0x0405 and self.balloon == "update":
                self.start_update()
            return 0
        if msg == self.WM_OPEN_APP:
            self.open_app()
            return 0
        if msg == self.WM_SYNC:
            self.refresh()
            self._changed()
            return 0
        if msg == self.WM_UPDATE:
            self.balloon = "update"
            self.refresh((tr("update_title", version=self.clock.new_version), tr("update_text")))
            if self.flyout and self.painter:
                self._fit_flyout()
            if self.app:
                self.app.invalidate()
            return 0
        if msg == self.WM_CHECKED:
            self.checking, self.check_time = False, time.monotonic()
            if self.flyout and self.painter:
                user32.KillTimer(self.flyout, 1)
                self._fit_flyout()
            if self.app:
                self.app.invalidate()
            return 0
        if msg == self.WM_CLOSE_APP:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:                                          # WM_DESTROY
            shell32.Shell_NotifyIconW(2, byref(self._nid()))
            user32.PostQuitMessage(0)
            return 0
        if msg == 0x0016 and wparam:                               # WM_ENDSESSION: hand the lighting back
            k32.SetEvent(self.stop.h)
            if self.worker:
                self.worker.join(3)
            shell32.Shell_NotifyIconW(2, byref(self._nid()))
            return 0
        if self.taskbar_created and msg == self.taskbar_created:
            shell32.Shell_NotifyIconW(0, byref(self._nid()))
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---- the panel
    def _menu(self):
        if self.flyout and user32.IsWindow(self.flyout):
            user32.PostMessageW(self.flyout, 0x0010, 0, 0)
        elif time.monotonic() - self.flyout_closed > 0.3:
            self._open_flyout()

    def _items(self):
        c, s = self.clock, self.clock.settings
        status, dot = self.status()
        icons = MenuPainter.ICONS
        items = [dict(kind="header", status=status, state=dot)]
        if c.new_version:
            items.append(dict(kind="action", id=25, icon="sync", text=tr("update_to", version=c.new_version),
                              accent=True, highlight=True, link=True))
        paused = c.paused()
        items += [dict(kind="action", id=29, icon="window", text=tr("open_app")),
                  dict(kind="sep"),
                  dict(kind="toggle", id=1, icon="clock", text=tr("clock"), on=s["enabled"]),
                  dict(kind="action", id=2, icon="light", text=tr("show_now")),
                  dict(kind="action", id=3, icon="sync" if paused else "pause",
                       text=tr("resume") if paused else tr("pause_hour")),
                  dict(kind="sep"), dict(kind="label", text=tr("display")),
                  dict(kind="segments", id=11, icon=AppWindow.MODE_ICONS.get(s["display"]["mode"], "clock"),
                       text=tr("mode_" + s["display"]["mode"]), values=self.MODES, value=s["display"]["mode"], seg_w=34,
                       glyphs=[icons[AppWindow.MODE_ICONS[m]] for m in self.MODES]),
                  dict(kind="segments", id=10, icon="sun", text=tr("brightness"), values=(25, 50, 75, 100),
                       value=round(s["look"]["brightness"])),
                  dict(kind="sep"),
                  dict(kind="toggle", id=20, icon="power", text=tr("start_windows"), on=self.autostart),
                  dict(kind="sep"), dict(kind="label", text=tr("about")),
                  dict(kind="action", id=26, icon="sync", text=tr("updates"), busy=self.checking,
                       status=self._check_status(), statuses=(tr("up_to_date"), tr("check_failed"), "v00.00.00")),
                  dict(kind="toggle", id=24, icon="clock", text=tr("auto_check"), on=s["check_updates"]),
                  dict(kind="action", id=23, icon="person", text=tr("made_by", author=AUTHOR), link=True),
                  dict(kind="action", id=22, icon="star", text=tr("star"), accent=True, link=True),
                  dict(kind="action", id=21, icon="doc", text=tr("open_log")),
                  dict(kind="sep"),
                  dict(kind="action", id=99, icon="quit", text=tr("quit"))]
        for i, it in enumerate(items):
            if i == self.hover:
                it["hover_seg"] = self.hover_seg
        return items

    def _fit_flyout(self):
        _, w, h = self._layout()
        pt, work, screen, bar = self.fly_place
        x, y = dock_flyout(pt, w, h, self.painter.px(12), work, screen, bar)
        user32.SetWindowPos(self.flyout, None, x, y, w, h, 0x0014)
        user32.InvalidateRect(self.flyout, None, False)

    def _layout(self):
        p = self.painter.px
        rows, y, width = [], p(6), 0
        for it in self._items():
            m = MEASUREITEMSTRUCT()
            self.painter.measure(m, it)
            rows.append((y, y + m.itemHeight))
            y += m.itemHeight
            width = max(width, m.itemWidth)
        return rows, width + p(12), y + p(6)

    def _open_flyout(self, pt=None):
        if pt is None:
            pt = wt.POINT()
            user32.GetCursorPos(byref(pt))
        mon, bar = user32.MonitorFromPoint(pt, 2), taskbar()
        if bar and user32.MonitorFromRect(byref(bar[1]), 2) != mon:
            mon = user32.MonitorFromRect(byref(bar[1]), 2)
            pt = wt.POINT(bar[1].right - 1, bar[1].bottom - 1)
        dpi_x, dpi_y = wt.UINT(96), wt.UINT(96)
        if shcore:
            shcore.GetDpiForMonitor(mon, 0, byref(dpi_x), byref(dpi_y))
        scale = dpi_x.value / 96.0
        size = round(28 * scale)
        self.flyout_icon = user32.LoadImageW(None, self.icon_path, 1, size, size, 0x10)
        self.painter = MenuPainter(scale, self.flyout_icon)
        self.autostart = autostart_enabled()
        self.hover, self.hover_seg, self.tracking = None, None, False
        rows, w, h = self._layout()
        mi = MONITORINFOEXW()
        mi.cbSize = sizeof(mi)
        user32.GetMonitorInfoW(mon, byref(mi))
        self.fly_place = (pt, mi.rcWork, mi.rcMonitor, bar)
        x, y = dock_flyout(pt, w, h, self.painter.px(12), mi.rcWork, mi.rcMonitor, bar)
        hinst = k32.GetModuleHandleW(None)
        self.flyout = user32.CreateWindowExW(0x00000080 | 0x00000008, "KeyboardClockFlyout", APP, 0x80000000,
                                             x, y, w, h, None, None, hinst, None)
        if not self.flyout:
            self.painter.close()
            self.painter = None
            return
        for attr, value in ((20, 1), (33, 2), (34, _cref(0x2C2E38))):
            v = wt.DWORD(value)
            dwmapi.DwmSetWindowAttribute(self.flyout, attr, byref(v), 4)
        user32.ShowWindow(self.flyout, 5)
        user32.SetForegroundWindow(self.flyout)
        if self.checking:
            user32.SetTimer(self.flyout, 1, 33, None)

    def _hit(self, x, y):
        rows, _, _ = self._layout()
        items = self._items()
        rc = wt.RECT()
        user32.GetClientRect(self.flyout, byref(rc))
        l, r = self.painter.px(6), rc.right - self.painter.px(6)
        for i, (t, b) in enumerate(rows):
            if t <= y < b:
                seg = None
                if items[i]["kind"] == "segments":
                    for k, (x0, y0, x1, y1) in enumerate(self.painter.segment_rects(items[i], l, t, r, b)):
                        if x0 <= x < x1:
                            seg = k
                elif items[i]["kind"] == "header":
                    x0, y0, x1, y1 = self.painter.close_rect(l, t, r, b)
                    if x0 <= x < x1 and y0 <= y < y1:
                        seg = "close"
                return i, seg
        return None, None

    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        rc = wt.RECT()
        user32.GetClientRect(hwnd, byref(rc))
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, rc.right, rc.bottom)
        old = gdi32.SelectObject(mem, bmp)
        user32.FillRect(mem, byref(rc), self.painter.bg_brush)
        rows, _, _ = self._layout()
        pad = self.painter.px(6)
        for i, (it, (t, b)) in enumerate(zip(self._items(), rows)):
            d = DRAWITEMSTRUCT()
            d.CtlType, d.hDC, d.rcItem = 1, mem, wt.RECT(pad, t, rc.right - pad, b)
            d.itemState = 1 if i == self.hover else 0
            self.painter.draw(d, it)
        gdi32.BitBlt(hdc, 0, 0, rc.right, rc.bottom, mem, 0, 0, 0x00CC0020)
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.EndPaint(hwnd, byref(ps))

    def _click(self, i, seg):
        items = self._items()
        if i is not None and items[i]["kind"] == "header" and seg == "close":
            user32.PostMessageW(self.flyout, 0x0010, 0, 0)
            return
        if i is None or "id" not in items[i]:
            return
        c, st, cid = self.clock, self.store, items[i]["id"]
        if cid == 1:
            st.set(("enabled",), not st.s["enabled"])
            self.refresh()
        elif cid == 3:
            c.pause(0 if c.paused() else 3600)
            self.refresh()
        elif cid == 20:
            set_autostart(not self.autostart, self.argv)
            self.autostart = autostart_enabled()
        elif cid == 24:
            st.set(("check_updates",), not st.s["check_updates"])
        elif cid == 11:
            if seg is not None:
                st.set(("display", "mode"), self.MODES[seg])
        elif cid == 10:
            if seg is not None:
                st.set(("look", "brightness"), items[i]["values"][seg])
        elif cid == 26:
            self.check_now()
        else:
            user32.PostMessageW(self.flyout, 0x0010, 0, 0)
            if cid == 2:
                c.show_for(15)
            elif cid == 21:
                os.startfile(LOG_PATH)
            elif cid == 22:
                os.startfile(REPO_URL)
            elif cid == 23:
                os.startfile(AUTHOR_URL)
            elif cid == 25:
                self.start_update()
            elif cid == 29:
                self.open_app()
            elif cid == 99:
                k32.SetEvent(self.stop.h)
            return
        user32.InvalidateRect(self.flyout, None, False)

    def _fly_proc(self, hwnd, msg, wparam, lparam):
        if msg == 0x000F and self.painter:
            self._paint(hwnd)
            return 0
        if msg == 0x0014:
            return 1
        if msg == 0x0113:
            if self.checking:
                user32.InvalidateRect(hwnd, None, False)
            else:
                user32.KillTimer(hwnd, 1)
            return 0
        if msg == 0x0200 and self.painter:
            x, y = ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value
            hit = self._hit(x, y)
            if hit != (self.hover, self.hover_seg):
                self.hover, self.hover_seg = hit
                user32.InvalidateRect(hwnd, None, False)
            if not self.tracking:
                tme = TRACKMOUSEEVENT(sizeof(TRACKMOUSEEVENT), 0x2, hwnd, 0)
                self.tracking = bool(user32.TrackMouseEvent(byref(tme)))
            return 0
        if msg == 0x02A3:
            self.tracking, self.hover, self.hover_seg = False, None, None
            user32.InvalidateRect(hwnd, None, False)
            return 0
        if msg == 0x0202 and self.painter:
            x, y = ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._click(*self._hit(x, y))
            return 0
        if msg == 0x0100 and wparam == 0x1B:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
            return 0
        if msg == 0x0006 and (wparam & 0xFFFF) == 0:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)
            return 0
        if msg == 0x0002:
            self.flyout, self.flyout_closed = None, time.monotonic()
            if self.painter:
                self.painter.close()
                self.painter = None
            user32.DestroyIcon(self.flyout_icon)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


# ---- updates from GitHub releases (checked against SHA256SUMS.txt)
def latest_release():
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO_URL.split('github.com/')[1]}/releases/latest",
                                 headers={"User-Agent": f"KeyboardClock/{__version__}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    return dict(version=data.get("tag_name", "").lstrip("vV"), page=data.get("html_url") or REPO_URL + "/releases/latest",
                assets=assets)


def install_kind():
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
        return "installer" if os.path.exists(os.path.join(here, "unins000.exe")) else "portable"
    return "pip" if "site-packages" in os.path.abspath(__file__).lower() else "script"


def _fetch(url, dest=None):
    import urllib.request
    if not url.startswith(("https://github.com/", "https://objects.githubusercontent.com/")):
        raise OSError("unexpected download location")
    req = urllib.request.Request(url, headers={"User-Agent": f"KeyboardClock/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if dest is None:
            return r.read()
        h = hashlib.sha256()
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
        return h.hexdigest()


def apply_update(info):
    import shutil
    import subprocess
    import tempfile
    kind = install_kind()
    assets = info["assets"]
    if kind == "installer":
        name = "KeyboardClockSetup.exe"
    elif kind == "portable":
        name = os.path.basename(sys.executable) if os.path.basename(sys.executable) in assets else "KeyboardClockPortable.exe"
    elif kind == "pip":
        name = next((n for n in assets if n.endswith(".whl")), "")
    else:
        name = "keyboard_clock.py"
    if name not in assets or "SHA256SUMS.txt" not in assets:
        raise OSError("no download for this kind of install")
    sums = _fetch(assets["SHA256SUMS.txt"]).decode("utf-8", "replace")
    expected = next((ln.split()[0].lower() for ln in sums.splitlines()
                     if len(ln.split()) == 2 and ln.split()[1].lstrip("*") == name), None)
    tmp = tempfile.mkdtemp(prefix="keyboard-clock-update-")
    dest = os.path.join(tmp, name)
    if not expected or _fetch(assets[name], dest) != expected:
        raise OSError("checksum mismatch")
    flags = 0x00000008 | 0x00000200
    if kind == "installer":
        subprocess.Popen([dest, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"],
                         creationflags=flags, close_fds=True)
        return
    if kind == "pip":
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--no-deps", "--disable-pip-version-check",
                        dest], check=True, creationflags=0x08000000, capture_output=True)
    else:
        current = sys.executable if kind == "portable" else os.path.abspath(__file__)
        old = current + ".old"
        if os.path.exists(old):
            os.remove(old)
        os.rename(current, old)
        shutil.copyfile(dest, current)
    subprocess.Popen(launch_command(["--after-update"]), creationflags=flags, close_fds=True)


def _version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def update_url(clock):
    if getattr(sys, "frozen", False) and os.path.exists(os.path.join(os.path.dirname(sys.executable), "unins000.exe")):
        return REPO_URL + "/releases/latest/download/KeyboardClockSetup.exe"
    return clock.update_page or REPO_URL + "/releases/latest"


def update_checker(clock, stop, notify):
    if stop.wait(30):
        return
    while True:
        if clock.check_updates:
            try:
                info = latest_release()
                tag = info["version"]
                if tag and _version_tuple(tag) > _version_tuple(__version__) and clock.new_version != tag:
                    clock.new_version, clock.update_page, clock.update_info = tag, info["page"], info
                    log(f"Update available: {tag}")
                    notify()
            except Exception as e:
                log(f"Update check skipped ({e.__class__.__name__})")
        if stop.wait(24 * 3600):
            return


def gdip_hgrad(g, colors, x, y, w, h, r, alpha=255):
    """Fills a rounded rectangle with a left-to-right gradient through `colors`, evenly spaced."""
    if w <= 0 or h <= 0 or not colors:
        return
    colors = list(colors) if len(colors) > 1 else [colors[0], colors[0]]
    n, brush = len(colors), VP()
    p1, p2 = POINTF(x - 1, y), POINTF(x + w + 1, y)  # a pixel beyond each end: no wrapped colour at the edges
    if gdiplus.GdipCreateLineBrush(byref(p1), byref(p2), Gfx.argb(colors[0], alpha), Gfx.argb(colors[-1], alpha), 0,
                                   byref(brush)):
        return
    blend = (ctypes.c_uint32 * n)(*(Gfx.argb(c, alpha) for c in colors))
    pos = (F * n)(*(i / (n - 1) for i in range(n)))
    gdiplus.GdipSetLinePresetBlend(brush, blend, pos, n)
    path = Gfx.round_path(x, y, w, h, r)
    gdiplus.GdipFillPath(g, brush, path)
    gdiplus.GdipDeletePath(path)
    gdiplus.GdipDeleteBrush(brush)


class Gfx:
    """GDI+ with alpha on a device context: rounded fills and outlines, circles, soft glows, gradients, pictures,
    clipping."""

    def __init__(self, hdc, clip=None):
        self.g, self.base = VP(), clip  # clip (l, t, r, b): only that part is painted
        self.ok = bool(_gdip_start()) and gdiplus.GdipCreateFromHDC(hdc, byref(self.g)) == 0
        if self.ok:
            gdiplus.GdipSetSmoothingMode(self.g, 4)  # antialiased
            gdiplus.GdipSetPixelOffsetMode(self.g, 4)
            self._base(0)

    def _base(self, mode):
        """Back to (mode 0), or within (mode 1), the part being painted."""
        if self.base:
            l, t, r, b = self.base
            gdiplus.GdipSetClipRectI(self.g, l, t, r - l, b - t, mode)
        elif mode == 0:
            gdiplus.GdipResetClip(self.g)

    def close(self):
        if self.ok:
            gdiplus.GdipDeleteGraphics(self.g)
            self.ok = False

    @staticmethod
    def argb(color, alpha=255):
        return ((int(alpha) & 0xFF) << 24) | (color & 0xFFFFFF)

    @staticmethod
    def round_path(x, y, w, h, r):
        path = VP()
        gdiplus.GdipCreatePath(0, byref(path))
        d = max(0.5, min(2.0 * r, w, h))
        gdiplus.GdipAddPathArc(path, x, y, d, d, 180, 90)
        gdiplus.GdipAddPathArc(path, x + w - d, y, d, d, 270, 90)
        gdiplus.GdipAddPathArc(path, x + w - d, y + h - d, d, d, 0, 90)
        gdiplus.GdipAddPathArc(path, x, y + h - d, d, d, 90, 90)
        gdiplus.GdipClosePathFigure(path)
        return path

    def _glow(self, g, color, cx, cy, rx, ry, alpha):
        path, brush = VP(), VP()
        gdiplus.GdipCreatePath(0, byref(path))
        gdiplus.GdipAddPathEllipse(path, cx - rx, cy - ry, 2 * rx, 2 * ry)
        if gdiplus.GdipCreatePathGradientFromPath(path, byref(brush)) == 0:
            gdiplus.GdipSetPathGradientCenterColor(brush, self.argb(color, alpha))
            edge, n = ctypes.c_uint32(self.argb(color, 0)), ctypes.c_int(1)
            gdiplus.GdipSetPathGradientSurroundColorsWithCount(brush, byref(edge), byref(n))
            gdiplus.GdipSetPathGradientSigmaBlend(brush, 1.0, 1.0)
            gdiplus.GdipFillPath(g, brush, path)
            gdiplus.GdipDeleteBrush(brush)
        gdiplus.GdipDeletePath(path)

    def draw(self, shape):
        if not self.ok:
            return
        kind = shape[0]
        if kind in ("round", "circle"):  # ("round", color, x, y, w, h, radius[, alpha]) / ("circle", color, x, y, d[, alpha])
            if kind == "round":
                _, color, x, y, w, h, r, *a = shape
            else:
                _, color, x, y, w, *a = shape
                h, r = w, w / 2
            if w <= 0 or h <= 0:
                return
            brush = VP()
            gdiplus.GdipCreateSolidFill(self.argb(color, a[0] if a else 255), byref(brush))
            if kind == "circle":
                gdiplus.GdipFillEllipse(self.g, brush, x, y, w, h)
            else:
                path = self.round_path(x, y, w, h, r)
                gdiplus.GdipFillPath(self.g, brush, path)
                gdiplus.GdipDeletePath(path)
            gdiplus.GdipDeleteBrush(brush)
        elif kind == "outline":  # ("outline", color, x, y, w, h, radius, width[, alpha])
            _, color, x, y, w, h, r, width, *a = shape
            pen = VP()
            gdiplus.GdipCreatePen1(self.argb(color, a[0] if a else 255), width, 2, byref(pen))  # UnitPixel
            half = width / 2
            path = self.round_path(x + half, y + half, w - width, h - width, max(0.5, r - half))
            gdiplus.GdipDrawPath(self.g, pen, path)
            gdiplus.GdipDeletePath(path)
            gdiplus.GdipDeletePen(pen)
        elif kind == "glow":  # ("glow", color, cx, cy, rx, ry, alpha): light that fades out, like on a wall
            self._glow(self.g, *shape[1:])
        elif kind == "glows":  # ("glows", [(color, cx, cy, rx, ry, alpha)], x0, y0, x1, y1): glows, drawn at a
            _, items, x0, y0, x1, y1 = shape  # quarter of the size then stretched (it is all blur): much faster
            if not items:
                return
            x = max(x0, min(cx - rx for _, cx, cy, rx, ry, _ in items))  # only where there is light
            y = max(y0, min(cy - ry for _, cx, cy, rx, ry, _ in items))
            w = min(x1, max(cx + rx for _, cx, cy, rx, ry, _ in items)) - x
            h = min(y1, max(cy + ry for _, cx, cy, rx, ry, _ in items)) - y
            k, bmp, g2 = 4.0, VP(), VP()
            bw, bh = max(1, int(w / k) + 2), max(1, int(h / k) + 2)
            if gdiplus.GdipCreateBitmapFromScan0(bw, bh, 0, 0xE200B, None, byref(bmp)) == 0:  # 32bppPARGB
                if gdiplus.GdipGetImageGraphicsContext(bmp, byref(g2)) == 0:
                    for color, cx, cy, rx, ry, alpha in items:
                        self._glow(g2, color, (cx - x) / k, (cy - y) / k, rx / k, ry / k, alpha)
                    gdiplus.GdipDeleteGraphics(g2)
                    gdiplus.GdipSetInterpolationMode(self.g, 6)  # high quality bilinear: here the fastest smooth one
                    gdiplus.GdipDrawImageRect(self.g, bmp, x, y, bw * k, bh * k)
                gdiplus.GdipDisposeImage(bmp)
        elif kind == "arc":  # ("arc", color, x, y, d, start, sweep, width): loaders
            _, color, x, y, d, start, sweep, width = shape
            pen = VP()
            gdiplus.GdipCreatePen1(self.argb(color), width, 2, byref(pen))
            gdiplus.GdipSetPenStartCap(pen, 2)
            gdiplus.GdipSetPenEndCap(pen, 2)
            gdiplus.GdipDrawArc(self.g, pen, x, y, d, d, start, sweep)
            gdiplus.GdipDeletePen(pen)
        elif kind == "hgrad":  # ("hgrad", colors, x, y, w, h, radius[, alpha]): a gradient, left to right
            gdip_hgrad(self.g, *shape[1:])
        elif kind == "image":  # ("image", (width, height, BGRA rows), x, y, w, h, radius): the screen's picture
            _, (tw, th, data), x, y, w, h, r = shape
            bmp, saved = VP(), VP()
            if gdiplus.GdipCreateBitmapFromScan0(tw, th, tw * 4, 0x22009, data, byref(bmp)) == 0:  # 32bppRGB
                gdiplus.GdipCreateRegion(byref(saved))
                gdiplus.GdipGetClip(self.g, saved)
                path = self.round_path(x, y, w, h, r)
                gdiplus.GdipSetClipPath(self.g, path, 1)  # CombineModeIntersect: inside the card too
                gdiplus.GdipDeletePath(path)
                gdiplus.GdipSetInterpolationMode(self.g, 7)  # high quality bicubic
                gdiplus.GdipDrawImageRect(self.g, bmp, x, y, w, h)
                gdiplus.GdipSetClipRegion(self.g, saved, 0)
                gdiplus.GdipDeleteRegion(saved)
                gdiplus.GdipDisposeImage(bmp)
        elif kind == "clip":  # ("clip", x, y, w, h, radius): what follows stays inside
            _, x, y, w, h, r = shape
            path = self.round_path(x, y, w, h, r)
            gdiplus.GdipSetClipPath(self.g, path, 0)  # CombineModeReplace
            gdiplus.GdipDeletePath(path)
            self._base(1)
        elif kind == "unclip":
            self._base(0)


class InputDialog:
    """A small dark window asking for one line of text (the scrolling text). Runs its own loop until closed."""
    current = None

    def __init__(self, owner, k):
        self.owner, self.k, self.hwnd, self.edit, self.result, self.done = owner, k, None, None, None, False
        self._ref = WNDPROC(self._proc)
        self.cls = f"KeyboardClockInput{id(self)}"
        wc = WNDCLASSEXW()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = sizeof(wc), self._ref, k32.GetModuleHandleW(None), self.cls
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
        user32.RegisterClassExW(byref(wc))
        self.painter = MenuPainter(k, None)
        self.font = gdi32.CreateFontW(-round(14 * k), 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, ui_font_face())
        self.field_brush = gdi32.CreateSolidBrush(_cref(AppWindow.FIELD))
        self.bg_brush = gdi32.CreateSolidBrush(_cref(AppWindow.CARD))

    def px(self, v):
        return round(v * self.k)

    def ask(self, title, prompt, hint, value):
        p = self.px
        w, h = p(560), p(232)
        rc = wt.RECT()
        user32.GetWindowRect(self.owner, byref(rc))
        x, y = (rc.left + rc.right - w) // 2, (rc.top + rc.bottom - h) // 2
        self.title, self.prompt, self.hint = title, prompt, hint
        self.hwnd = user32.CreateWindowExW(0x00000001, self.cls, title, 0x80C80000, x, y, w, h, self.owner, None,
                                           k32.GetModuleHandleW(None), None)     # DLGMODALFRAME; POPUP|CAPTION|SYSMENU
        if not self.hwnd:
            return None
        for attr, v in ((20, 1), (35, _cref(AppWindow.CARD)), (34, _cref(0x2C2E38))):
            vv = wt.DWORD(v)
            dwmapi.DwmSetWindowAttribute(self.hwnd, attr, byref(vv), 4)
        cr = wt.RECT()
        user32.GetClientRect(self.hwnd, byref(cr))
        self.edit = user32.CreateWindowExW(0, "EDIT", value, 0x50010080, p(24), p(56), cr.right - p(48), p(30),
                                           self.hwnd, ctypes.c_void_p(100), k32.GetModuleHandleW(None), None)
        user32.SendMessageW(self.edit, 0x0030, self.font, 1)                      # WM_SETFONT
        user32.SendMessageW(self.edit, 0x00C5, 200, 0)                            # EM_LIMITTEXT
        user32.SendMessageW(self.edit, 0x00B1, 0, -1)                             # EM_SETSEL: all
        bw, bh = p(104), p(34)
        for cid, text, bx in ((1, tr("ok"), cr.right - p(24) - bw), (2, tr("cancel"), cr.right - p(24) - 2 * bw - p(10))):
            user32.CreateWindowExW(0, "BUTTON", text, 0x5001000B, bx, cr.bottom - p(20) - bh, bw, bh, self.hwnd,
                                   ctypes.c_void_p(cid), k32.GetModuleHandleW(None), None)   # BS_OWNERDRAW
        user32.EnableWindow(self.owner, False)
        user32.ShowWindow(self.hwnd, 5)
        user32.SetFocus(self.edit)
        InputDialog.current = self
        msg = wt.MSG()
        while not self.done and user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0100 and msg.wParam == 0x0D:                      # Enter
                self._close(True)
                continue
            if not user32.IsDialogMessageW(self.hwnd, byref(msg)):
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
        InputDialog.current = None
        for h_ in (self.font, self.field_brush, self.bg_brush):
            gdi32.DeleteObject(h_)
        self.painter.close()
        return self.result

    def _close(self, ok):
        if ok and self.edit:
            n = user32.GetWindowTextLengthW(self.edit)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(self.edit, buf, n + 1)
            self.result = buf.value
        user32.EnableWindow(self.owner, True)
        user32.DestroyWindow(self.hwnd)
        user32.SetForegroundWindow(self.owner)
        self.done = True

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == 0x000F:                                                     # WM_PAINT
                ps = PAINTSTRUCT()
                hdc = user32.BeginPaint(hwnd, byref(ps))
                rc = wt.RECT()
                user32.GetClientRect(hwnd, byref(rc))
                user32.FillRect(hdc, byref(rc), self.bg_brush)
                gdi32.SetBkMode(hdc, 1)
                p = self.px
                self.painter._text(hdc, self.prompt, self.painter.f_text, MenuPainter.TEXT, p(24), p(18), rc.right - p(24), p(48))
                hr = wt.RECT(p(24), p(96), rc.right - p(24), p(150))
                gdi32.SelectObject(hdc, self.painter.f_small)
                gdi32.SetTextColor(hdc, _cref(MenuPainter.MUTED))
                user32.DrawTextW(hdc, self.hint, -1, byref(hr), 0x10 | 0x800)
                user32.EndPaint(hwnd, byref(ps))
                return 0
            if msg == 0x0133:                                                     # WM_CTLCOLOREDIT
                gdi32.SetTextColor(wparam, _cref(MenuPainter.TEXT))
                gdi32.SetBkColor(wparam, _cref(AppWindow.FIELD))
                return self.field_brush
            if msg == 0x002B:                                                     # WM_DRAWITEM: our buttons
                dis = DRAWITEMSTRUCT.from_address(lparam)
                rc = dis.rcItem
                primary = dis.CtlID == 1
                pressed = dis.itemState & 0x1
                user32.FillRect(dis.hDC, byref(rc), self.bg_brush)
                fill = (0x7558F0 if pressed else MenuPainter.ACCENT) if primary else (0x23252D if pressed else 0x272932)
                self.painter._shapes(dis.hDC, [("round", fill, rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top,
                                                self.px(7))])
                gdi32.SetBkMode(dis.hDC, 1)
                self.painter._text(dis.hDC, tr("ok") if primary else tr("cancel"), self.painter.f_text,
                                   0xFFFFFF if primary else MenuPainter.TEXT, rc.left, rc.top, rc.right, rc.bottom, 0x1)
                return 1
            if msg == 0x0111:                                                     # WM_COMMAND
                cid = wparam & 0xFFFF
                if cid in (1, 2):
                    self._close(cid == 1)
                    return 0
            if msg == 0x0010:                                                     # WM_CLOSE
                self._close(False)
                return 0
        except Exception as e:
            log(f"Input dialog: {e!r}")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def keycap(c, base=0x1C1E25):
    """An LED color seen on a dark keycap."""
    b = ((base >> 16) & 255, (base >> 8) & 255, base & 255)
    out = [int(b[i] + c[i] * (255 - b[i]) / 255) for i in range(3)]
    return (out[0] << 16) | (out[1] << 8) | out[2]


def theme_stops(name):
    th = THEMES[name]
    if th.get("gradient"):
        return [cint(c) for c in th["gradient"]]
    if th.get("style") == "rainbow":
        return [hsv_color(a * 60, 1) for a in range(6)]
    if th.get("style") == "daytime":
        return [cint(c) for _, c in DAYTIME[1:-1]]
    colors = th.get("colors", {})
    return [cint(colors.get("hours", "#ffffff")), cint(colors.get("minutes", "#ffffff"))]


class AppWindow:
    """The window: a sidebar of pages, drawn from display lists rebuilt on every paint (Glowback's toolkit).
    Pages: Clock (live keyboard, what it shows), Look, When, Font (digit editor), Keyboard, Settings, About."""
    PAGES = (("clock", "clock", "nav_clock"), ("look", "palette", "nav_look"), ("when", "timer", "nav_when"),
             ("font", "font", "nav_font"), ("keyboard", "keyboard", "nav_keyboard"),
             ("settings", "settings", "nav_settings"), ("about", "info", "nav_about"))
    LIVE_PAGES = ("clock", "look")
    MODE_ICONS = {"time": "clock", "time_date": "calendar", "scroll": "arrow", "mixed": "layers", "custom": "edit"}
    SLIDERS = ("secs", "speed", "hue", "sat", "bghue", "bgsat", "bg_level", "brightness", "night_bright")
    BG, CARD, LINE, HOVER, SELECT = 0x121317, 0x1A1B21, 0x24262E, 0x212329, 0x1F2129
    FIELD, FIELD_LINE = 0x0F1013, 0x2E3140
    SIZE, MIN = (1060, 820), (860, 580)
    LANG_NAMES = (("", None), ("en", "English"), ("fr", "Français"), ("es", "Español"), ("de", "Deutsch"),
                  ("it", "Italiano"), ("pt", "Português (Brasil)"))
    DELAYS = (10, 20, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1800)
    OFF_AFTER = (0, 5, 10, 15, 30, 45, 60, 120)
    HOTKEYS = ("Ctrl+Alt+H", "Ctrl+Alt+K", "Ctrl+Alt+C", "Ctrl+Shift+F12", "Win+Alt+K", "")
    TEXTS = (("{time}", "text_time"), ("{time} · {weekday} {date}", "text_time_date"), ("{weekday} {date}", "text_date"),
             ("{time}:{seconds}", "text_seconds"))

    def __init__(self, tray):
        self.tray, self.clock, self.store = tray, tray.clock, tray.store
        self.hwnd = self.painter = self.icon = self.icon_big = None
        self.k, self.fonts, self.size = 1.0, {}, (0, 0)
        self.page, self.scroll, self.max_scroll = "clock", 0, 0
        self.widgets, self.side, self.content = [], ([], []), ([], [])
        self.hover = self.pressed = self.focus = self.drag = None
        self.focus_visible = self.tracking = False
        self.menu_items = []
        self.role, self.digit_side, self.stop_sel, self.hue_memo = "hours", 0, 0, None
        self.font_digit, self.font_side = "1", 0
        self.bufs, self.preview_rect = None, None
        self.sw = self.cx0 = self.cx1 = 0
        self.t0 = time.monotonic()
        self._model = self._renderer = self._rver = None
        self._ref = WNDPROC(self._proc)
        self.cls = f"KeyboardClockApp{id(self)}"
        wc = WNDCLASSEXW()
        wc.cbSize, wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = sizeof(wc), self._ref, k32.GetModuleHandleW(None), self.cls
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
        icon = ensure_icons()[0]
        wc.hIcon = user32.LoadImageW(None, icon, 1, 48, 48, 0x10)
        wc.hIconSm = user32.LoadImageW(None, icon, 1, 16, 16, 0x10)
        user32.RegisterClassExW(byref(wc))

    # ---- scale, fonts, opening
    def px(self, v):
        return round(v * self.k)

    def set_scale(self, k):
        self._free_gdi()
        self.k = k
        self.painter = MenuPainter(k, None)
        face, glyphs = ui_font_face(), icon_font_face()
        mk = lambda size, weight, f=face: gdi32.CreateFontW(-round(size * k), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, f)
        self.fonts = dict(page=mk(26, 600), h2=mk(15, 600), nav=mk(14, 400), body=mk(14, 400), button=mk(13.5, 600),
                          name=mk(17, 600), hero=mk(30, 600), icon=mk(18, 400, glyphs), icon_s=mk(14, 400, glyphs),
                          icon_l=mk(22, 400, glyphs))
        path = ensure_icons()[0]
        self.icon = user32.LoadImageW(None, path, 1, self.px(32), self.px(32), 0x10)
        self.icon_big = user32.LoadImageW(None, path, 1, self.px(72), self.px(72), 0x10)

    def _free_gdi(self):
        for f in self.fonts.values():
            gdi32.DeleteObject(f)
        self.fonts = {}
        if self.painter:
            self.painter.close()
            self.painter = None
        for h in (self.icon, self.icon_big):
            if h:
                user32.DestroyIcon(h)
        self.icon = self.icon_big = None

    def open(self, page=None):
        if page:
            self.page, self.scroll = page, 0
        if page == "settings" or not self.hwnd:
            self.tray.autostart = autostart_enabled()
        if self.hwnd and user32.IsWindow(self.hwnd):
            user32.ShowWindow(self.hwnd, 9 if user32.IsIconic(self.hwnd) else 5)
            user32.SetForegroundWindow(self.hwnd)
            self._timers()
            self.invalidate()
            return
        pt = wt.POINT()
        user32.GetCursorPos(byref(pt))
        mon = user32.MonitorFromPoint(pt, 2)
        dpi_x, dpi_y = wt.UINT(96), wt.UINT(96)
        if shcore:
            shcore.GetDpiForMonitor(mon, 0, byref(dpi_x), byref(dpi_y))
        self.set_scale(dpi_x.value / 96.0)
        mi = MONITORINFOEXW()
        mi.cbSize = sizeof(mi)
        user32.GetMonitorInfoW(mon, byref(mi))
        work = mi.rcWork
        w = min(self.px(self.SIZE[0]), work.right - work.left - self.px(32))
        h = min(self.px(self.SIZE[1]), work.bottom - work.top - self.px(32))
        x, y = work.left + (work.right - work.left - w) // 2, work.top + (work.bottom - work.top - h) // 2
        self.hwnd = user32.CreateWindowExW(0, self.cls, APP, 0x00CF0000, x, y, w, h, None, None,
                                           k32.GetModuleHandleW(None), None)
        if not self.hwnd:
            self._free_gdi()
            log(f"App window: Windows refused it ({ctypes.get_last_error()})")
            return
        for attr, value in ((20, 1), (35, _cref(self.BG)), (34, _cref(0x2C2E38))):
            v = wt.DWORD(value)
            dwmapi.DwmSetWindowAttribute(self.hwnd, attr, byref(v), 4)
        user32.ShowWindow(self.hwnd, 5)
        user32.SetForegroundWindow(self.hwnd)
        self._timers()

    def invalidate(self):
        if self.hwnd:
            user32.InvalidateRect(self.hwnd, None, False)

    def _timers(self):
        if not self.hwnd:
            return
        if self.page in self.LIVE_PAGES and not user32.IsIconic(self.hwnd):
            user32.SetTimer(self.hwnd, 1, 40, None)            # the live keyboard, 25 frames a second
        else:
            user32.KillTimer(self.hwnd, 1)
        user32.SetTimer(self.hwnd, 2, 1000, None)
        if self.tray.checking:
            user32.SetTimer(self.hwnd, 3, 33, None)

    # ---- display lists
    def S(self, *shape, side=False):
        (self.side if side else self.content)[0].append(shape)

    def T(self, text, font, color, l, t, r, b, flags=0, side=False):
        (self.side if side else self.content)[1].append(("text", text, font, color, l, t, r, b, flags))

    def W(self, text, font, color, l, t, r, b):
        self.content[1].append(("wrap", text, font, color, l, t, r, b))

    def I(self, hicon, x, y, size, side=False):
        (self.side if side else self.content)[1].append(("icon", hicon, x, y, size))

    def add(self, wid, kind, rect, side=False, focus=True, **kw):
        self.widgets.append(dict(id=wid, kind=kind, rect=tuple(int(v) for v in rect), side=side, focus=focus, **kw))

    def tw(self, text, font):
        return self.painter.text_width(text, font)

    def wrap_h(self, text, font, width):
        rc = wt.RECT(0, 0, int(width), 0)
        gdi32.SelectObject(self.painter.mdc, font)
        user32.DrawTextW(self.painter.mdc, text, -1, byref(rc), 0x10 | 0x400 | 0x800)
        return rc.bottom

    # ---- building blocks (Glowback's), then ours
    def _status(self):
        text, dot = self.tray.status()
        return text, {"on": MenuPainter.GREEN, "off": MenuPainter.OFF + 0x202020, "none": MenuPainter.AMBER}[dot]

    def _nav(self, wid, x, y, w, icon, text, selected, quiet=False):
        p, h, ic = self.px, self.px(38), MenuPainter.ICONS
        hov = self.hover == wid
        if selected:
            self.S("round", self.SELECT, x, y, w, h, p(7), side=True)
            self.S("round", MenuPainter.ACCENT, x + p(1), y + h / 2 - p(8), p(3), p(16), p(1.5), side=True)
        elif hov:
            self.S("round", 0x1B1C22, x, y, w, h, p(7), side=True)
        color = MenuPainter.MUTED if quiet and not hov else MenuPainter.TEXT
        glyph = MenuPainter.LABEL if selected else (color if quiet else MenuPainter.ICON)
        self.T(ic[icon], self.fonts["icon"], glyph, x + p(10), y, x + p(40), y + h, 0x1, side=True)
        self.T(text, self.fonts["nav"], color, x + p(48), y, x + w - p(8), y + h, 0x8000, side=True)
        self.add(wid, "nav", (x, y, x + w, y + h), side=True, radius=p(7))

    def _card(self, y, h, x0=None, x1=None):
        p = self.px
        x0 = self.cx0 if x0 is None else x0
        x1 = self.cx1 if x1 is None else x1
        self.S("round", self.CARD, x0, y, x1 - x0, h, p(10))
        self.S("outline", self.LINE, x0, y, x1 - x0, h, p(10), max(1.0, self.k))

    def _sep(self, y):
        self.S("round", self.LINE, self.cx0 + self.px(16), y, self.cx1 - self.cx0 - self.px(32), max(1, self.px(1)), 0)

    def _row_hover(self, wid, y, h):
        if self.hover == wid:
            p = self.px
            self.S("round", self.HOVER, self.cx0 + p(4), y + p(4), self.cx1 - self.cx0 - p(8), h - p(8), p(7))

    def _header(self, y, title, sub=None):
        p = self.px
        self.T(title, self.fonts["page"], MenuPainter.TEXT, self.cx0, y, self.cx1, y + p(40))
        y += p(44)
        if sub:
            h = self.wrap_h(sub, self.fonts["body"], self.cx1 - self.cx0)
            self.W(sub, self.fonts["body"], MenuPainter.MUTED, self.cx0, y, self.cx1, y + h)
            y += h
        return y + p(24)

    def _label(self, y, text):
        p = self.px
        self.T(text.upper(), self.painter.f_label, MenuPainter.LABEL, self.cx0 + p(4), y, self.cx1, y + p(18))
        return y + p(26)

    def _row_text(self, y, h, icon, title, desc=None, right=None, icon_color=None, hicon=None, desc_color=None):
        p, ic = self.px, MenuPainter.ICONS
        x = self.cx0 + p(20)
        if hicon:
            self.I(hicon, x, y + (h - p(28)) / 2, p(28))
            x += p(44)
        elif icon:
            self.T(ic[icon], self.fonts["icon"], icon_color or MenuPainter.ICON, x, y, x + p(24), y + h, 0x1)
            x += p(42)
        r = self.cx1 - p(20) if right is None else right
        if desc:
            self.T(title, self.fonts["body"], MenuPainter.TEXT, x, y + p(10), r, y + h / 2 + p(2), 0x8000)
            self.T(desc, self.painter.f_small, desc_color or MenuPainter.MUTED, x, y + h / 2 + p(1), r, y + h - p(9), 0x8000)
        else:
            self.T(title, self.fonts["body"], MenuPainter.TEXT, x, y, r, y + h, 0x8000)

    def _toggle(self, wid, x, y, on, row=None):
        p = self.px
        w, h = p(42), p(22)
        hov = self.hover == wid
        if on:
            self.S("round", 0x9A80FF if hov else MenuPainter.ACCENT, x, y, w, h, h / 2)
            d = h - p(8)
            self.S("circle", 0xFFFFFF, x + w - d - p(4), y + p(4), d)
        else:
            edge = 0xC5C9D4 if hov else 0x8C91A1
            self.S("outline", edge, x, y, w, h, h / 2, max(1.0, self.k * 1.2))
            d = h - p(10)
            self.S("circle", edge, x + p(5), y + p(5), d)
        self.add(wid, "toggle", (x, y, x + w, y + h), radius=h / 2)
        if row:  # the whole row switches it too
            self.add(wid, "toggle", row, focus=False)

    def _button(self, wid, right, y, text, style="secondary", icon=None, busy=False, h=None):
        """A button right-aligned on `right`; returns its left edge."""
        p, ic = self.px, MenuPainter.ICONS
        h = h or p(34)
        f = self.fonts["button"]
        w = self.tw(text, f) + p(30) + (p(24) if icon or busy else 0)
        x = right - w
        hov, prs = self.hover == wid, self.pressed == wid
        if style == "primary":
            fill, color = (0x7558F0 if prs else 0x9A80FF if hov else MenuPainter.ACCENT), 0xFFFFFF
        elif style == "quiet":
            fill, color = (0x25272F if prs else 0x202229 if hov else None), (MenuPainter.TEXT if hov else MenuPainter.ICON)
        else:
            fill, color = (0x23252D if prs else 0x2E303A if hov else 0x272932), MenuPainter.TEXT
        if fill is not None:
            self.S("round", fill, x, y, w, h, p(7))
        if style == "secondary":
            self.S("outline", 0x363843, x, y, w, h, p(7), max(1.0, self.k))
        tx = x + p(15)
        if busy:
            d, width, now = p(14), max(1.5, self.k * 1.8), time.monotonic()
            sweep = 40 + 230 * (0.5 - 0.5 * math.cos(now * 2 * math.pi / 1.6))
            self.S("arc", MenuPainter.LINE, tx, y + (h - d) / 2, d, 0, 360, width)
            self.S("arc", MenuPainter.ACCENT, tx, y + (h - d) / 2, d, (now * 320) % 360, sweep, width)
            tx += p(24)
        elif icon:
            self.T(ic[icon], self.fonts["icon_s"], color, tx, y, tx + p(16), y + h, 0x1)
            tx += p(24)
        self.T(text, f, color, tx, y, x + w - p(12), y + h)
        self.add(wid, "button", (x, y, x + w, y + h), radius=p(7))
        return x

    def _picker(self, wid, x, y, w, text, hicon=None, glyph=None, swatch=None, stops=None, disabled=False):
        p, h, ic = self.px, self.px(36), MenuPainter.ICONS
        hov = self.hover == wid and not disabled
        self.S("round", self.FIELD, x, y, w, h, p(7))
        self.S("outline", 0x4A4E5E if hov else self.FIELD_LINE, x, y, w, h, p(7), max(1.0, self.k))
        tx = x + p(12)
        if hicon:
            self.I(hicon, tx, y + (h - p(20)) / 2, p(20))
            tx += p(28)
        elif swatch is not None:
            d = p(16)
            self.S("circle", swatch, tx + p(1), y + (h - d) / 2, d)
            tx += p(26)
        elif stops:
            self.S("hgrad", stops, tx, y + (h - p(12)) / 2, p(24), p(12), p(6))
            tx += p(32)
        elif glyph:
            self.T(ic[glyph], self.fonts["icon_s"], MenuPainter.MUTED if disabled else MenuPainter.ICON, tx, y,
                   tx + p(18), y + h, 0x1)
            tx += p(26)
        self.T(text, self.fonts["body"], MenuPainter.MUTED if disabled else MenuPainter.TEXT, tx, y, x + w - p(34),
               y + h, 0x8000)
        if not disabled:
            self.T(ic["chev_down"], self.fonts["icon_s"], MenuPainter.MUTED, x + w - p(32), y, x + w - p(10), y + h, 0x1)
            self.add(wid, "picker", (x, y, x + w, y + h), radius=p(7))

    def _slider(self, wid, x0, x1, cy, value, track=None, knob=None):
        """A 0-100 slider; `track`: colors of a gradient track (hue...), `knob`: the knob's color."""
        p = self.px
        fx = x0 + (x1 - x0) * max(0.0, min(100.0, value)) / 100
        if track is None:
            th = p(4)
            self.S("round", 0x3A3D49, x0, cy - th / 2, x1 - x0, th, th / 2)
            if fx > x0:
                self.S("round", MenuPainter.ACCENT, x0, cy - th / 2, fx - x0, th, th / 2)
        else:
            th = p(10)
            self.S("hgrad", track, x0, cy - th / 2, x1 - x0, th, th / 2)
        d = p(22)
        if knob is None:
            inner = p(12) if self.hover == wid or self.drag == wid else p(10)
            self.S("circle", 0x2B2D38, fx - d / 2, cy - d / 2, d)
            self.S("outline", 0x45485A, fx - d / 2, cy - d / 2, d, d, d / 2, max(1.0, self.k))
            self.S("circle", MenuPainter.ACCENT, fx - inner / 2, cy - inner / 2, inner)
        else:
            ring = p(4) if self.hover == wid or self.drag == wid else p(3)
            self.S("circle", 0xFFFFFF, fx - d / 2, cy - d / 2, d)
            self.S("circle", knob, fx - d / 2 + ring, cy - d / 2 + ring, d - 2 * ring)
        self.add(wid, "slider", (x0 - p(12), cy - p(16), x1 + p(12), cy + p(16)), x0=x0, x1=x1, radius=p(16))

    def _mode_tile(self, wid, x, y, w, h, icon, title, selected):
        """A compact choice: its icon over its name."""
        p, ic = self.px, MenuPainter.ICONS
        hov = self.hover == wid
        self.S("round", 0x1D1A30 if selected else (self.HOVER if hov else self.CARD), x, y, w, h, p(10))
        self.S("outline", MenuPainter.ACCENT if selected else self.LINE, x, y, w, h, p(10),
               max(1.5, p(2)) if selected else max(1.0, self.k))
        self.T(ic[icon], self.fonts["icon_l"], MenuPainter.LABEL if selected else MenuPainter.ICON, x, y + p(12), x + w,
               y + p(44), 0x1)
        self.T(title, self.fonts["body"], MenuPainter.TEXT, x + p(6), y + p(46), x + w - p(6), y + h - p(12), 0x1 | 0x8000)
        self.add(wid, "tile", (x, y, x + w, y + h), radius=p(10))

    def _swatch(self, wid, x, y, d, color=None, selected=False, stops=None, w=None):
        """A color (a disc) or a gradient (a pill) to pick; a ring shows the chosen one."""
        p = self.px
        w = w or d
        hov = self.hover == wid
        if selected or hov:
            g = p(4)
            self.S("outline", 0xFFFFFF if selected else 0x6B6F80, x - g, y - g, w + 2 * g, d + 2 * g, (d + 2 * g) / 2,
                   max(1.5, p(2)))
        if stops:
            self.S("hgrad", stops, x, y, w, d, d / 2)
        else:
            self.S("circle", color, x, y, d)
        self.add(wid, "swatch", (x - p(5), y - p(5), x + w + p(5), y + d + p(5)), radius=(d + p(10)) / 2)

    def _segmented(self, prefix, x0, x1, y, options, current):
        """Choices side by side, one of them on: options are (value, glyph, text)."""
        p, ic, h = self.px, MenuPainter.ICONS, self.px(40)
        self.S("round", self.FIELD, x0, y, x1 - x0, h, p(9))
        self.S("outline", self.FIELD_LINE, x0, y, x1 - x0, h, p(9), max(1.0, self.k))
        w = (x1 - x0 - p(8)) / len(options)
        for i, (value, glyph, text) in enumerate(options):
            sx, wid = x0 + p(4) + i * w, f"{prefix}:{value}"
            on = value == current
            if on:
                self.S("round", MenuPainter.ACCENT, sx, y + p(4), w, h - p(8), p(6))
            elif self.hover == wid:
                self.S("round", self.HOVER, sx, y + p(4), w, h - p(8), p(6))
            color = 0xFFFFFF if on else MenuPainter.ICON
            f = self.fonts["button"]
            full = self.tw(text, f) + (p(24) if glyph else 0)
            tx = sx + max(p(6), (w - full) / 2)
            if glyph and full < w - p(8):
                self.T(ic[glyph], self.fonts["icon_s"], color, tx, y, tx + p(18), y + h, 0x1)
                tx += p(24)
            self.T(text, f, color, tx, y, sx + w - p(4), y + h, 0x8000)
            self.add(wid, "tile", (sx, y + p(4), sx + w, y + h - p(4)), radius=p(6))

    def _stepper(self, wid, right, y, text):
        """[<] text [>], right-aligned on `right`: returns its left edge."""
        p, ic = self.px, MenuPainter.ICONS
        h, bw = p(36), p(34)
        w = 2 * bw + max(self.tw("00:00", self.fonts["body"]), self.tw(text, self.fonts["body"])) + p(14)
        x = right - w
        self.S("round", self.FIELD, x, y, w, h, p(7))
        self.S("outline", self.FIELD_LINE, x, y, w, h, p(7), max(1.0, self.k))
        for key, gx, glyph in (("-", x, "chev_left"), ("+", x + w - bw, "chev_right")):
            if self.hover == f"{wid}:{key}":
                self.S("round", self.HOVER, gx + p(3), y + p(3), bw - p(6), h - p(6), p(5))
            self.T(ic[glyph], self.fonts["icon_s"], MenuPainter.ICON, gx, y, gx + bw, y + h, 0x1)
            self.add(f"{wid}:{key}", "button", (gx, y, gx + bw, y + h), radius=p(7))
        self.T(text, self.fonts["body"], MenuPainter.TEXT, x + bw, y, x + w - bw, y + h, 0x1)
        return x

    def _icon_button(self, wid, x, y, size, glyph, enabled=True):
        p, ic = self.px, MenuPainter.ICONS
        hov = self.hover == wid and enabled
        self.S("round", 0x2E303A if hov else 0x272932, x, y, size, size, p(7))
        self.S("outline", 0x363843, x, y, size, size, p(7), max(1.0, self.k))
        self.T(ic[glyph], self.fonts["icon_s"], MenuPainter.TEXT if enabled else 0x4A4E5C, x, y, x + size, y + size, 0x1)
        if enabled:
            self.add(wid, "button", (x, y, x + size, y + size), radius=p(7))

    def _tile(self, wid, x, y, w, h, icon, title, desc, selected):
        p, ic = self.px, MenuPainter.ICONS
        hov = self.hover == wid
        self.S("round", 0x1D1A30 if selected else (self.HOVER if hov else self.CARD), x, y, w, h, p(10))
        self.S("outline", MenuPainter.ACCENT if selected else self.LINE, x, y, w, h, p(10),
               max(1.5, p(2)) if selected else max(1.0, self.k))
        self.S("round", 0x2A2448 if selected else 0x25272F, x + p(18), y + p(18), p(36), p(36), p(9))
        self.T(ic[icon], self.fonts["icon"], MenuPainter.LABEL if selected else MenuPainter.ICON,
               x + p(18), y + p(18), x + p(54), y + p(54), 0x1)
        tx = x + p(70)
        self.T(title, self.fonts["h2"], MenuPainter.TEXT, tx, y + p(16), x + w - p(48), y + p(40), 0x8000)
        dh = self.wrap_h(desc, self.painter.f_small, x + w - p(20) - tx)
        self.content[1].append(("wrap", desc, self.painter.f_small, MenuPainter.MUTED, tx, y + p(42), x + w - p(20),
                                y + p(42) + dh))
        d = p(18)
        rx, ry = x + w - p(18) - d, y + p(18)
        if selected:
            self.S("circle", MenuPainter.ACCENT, rx, ry, d)
            self.S("circle", 0xFFFFFF, rx + d / 2 - p(3.5), ry + d / 2 - p(3.5), p(7))
        else:
            self.S("outline", MenuPainter.RING, rx, ry, d, d, d / 2, max(1.2, self.k * 1.5))
        self.add(wid, "tile", (x, y, x + w, y + h), radius=p(10))

    def _card_behind(self, at, y, h):
        p, x0, x1 = self.px, self.cx0, self.cx1
        self.content[0][at:at] = [("round", self.CARD, x0, y, x1 - x0, h, p(10)),
                                  ("outline", self.LINE, x0, y, x1 - x0, h, p(10), max(1.0, self.k))]

    def _field_label(self, text, y, h, right):
        p = self.px
        self.T(text, self.fonts["body"], MenuPainter.ICON, self.cx0 + p(20), y, right - p(12), y + h, 0x8000)

    def _value(self, text, y, h):
        p = self.px
        self.T(text, self.fonts["body"], MenuPainter.TEXT, self.cx1 - p(96), y, self.cx1 - p(20), y + h, 0x2)

    def _toggle_row(self, wid, y, icon, title, desc, on, rh=None):
        p = self.px
        rh = rh or p(64)
        tx = self.cx1 - p(20) - p(42)
        self._toggle(wid, tx, y + (rh - p(22)) / 2, on, row=(self.cx0, y, self.cx1, y + rh))
        self._row_text(y, rh, icon, title, desc, right=tx - p(16))
        return y + rh

    def model(self):
        name = self.clock.model_name()
        if not self._model or self._model.name != name:
            self._model = Model(name)
        return self._model

    def renderer(self):
        m = self.model()
        if self._renderer is None or self._renderer.model is not m:
            self._renderer, self._rver = Renderer(m, self.store.s, self.clock.lang), self.clock.version
        elif self._rver != self.clock.version:
            self._renderer.configure(self.store.s)
            self._renderer.lang, self._rver = self.clock.lang, self.clock.version
        return self._renderer

    def live_frame(self):
        s, wall = self.store.s, dt.datetime.now()
        return self.renderer().frame(time.monotonic() - self.t0, wall, None, night_now(s["night"], wall))

    def font_frame(self, model=None, digit=None):
        """The digit being edited, on the left (hours color) and on the right (minutes color)."""
        s = self.store.s
        m = model or self.model()
        custom = s["display"]["custom_font"] if s["display"]["font"] == "custom" else None
        d = digit or self.font_digit
        frame = {k: (0, 0, 0) for k in m.keys}
        colors = s["look"]["colors"]
        for pos, role in ((0, "hours"), (1, "minutes")):
            for k in font_keys(m, d, pos, custom):
                frame[k] = hex_color(colors[role])
        return frame

    def _keyboard(self, x, y, w, frame, area=None):
        """The keyboard, with each key lit as in `frame`; keys of `area` become clickable. Returns its height."""
        p, m = self.px, self.model()
        u = w / (m.width + 0.64)
        ox, oy = x + 0.32 * u, y + 0.32 * u
        h = (m.height + 0.64) * u
        self.S("round", 0x0D0E12, x, y, w, h, 0.42 * u)
        self.S("outline", 0x23262F, x, y, w, h, 0.42 * u, max(1.0, self.k))
        at, glows = len(self.content[0]), []
        area = area or set()
        for k, kx, ky, kw, kh in m.rects:
            c = frame.get(k, (0, 0, 0))
            bx, by, bw, bh = ox + (kx + 0.06) * u, oy + (ky + 0.06) * u, (kw - 0.12) * u, (kh - 0.12) * u
            base = 0x2A2D38 if k in area else 0x1C1E25
            self.S("round", keycap(c, base), bx, by, bw, bh, 0.13 * u)
            if max(c) > 24:
                glows.append((cint(c), bx + bw / 2, by + bh / 2, bw * 0.75 + 0.45 * u, bh * 0.75 + 0.45 * u,
                              min(150, 40 + max(c) * 0.4)))
            if k in area:
                wid = "key:" + k
                if self.hover == wid:
                    self.S("outline", 0xFFFFFF, bx, by, bw, bh, 0.13 * u, max(1.5, p(2)), 200)
                self.add(wid, "key", (bx, by, bx + bw, by + bh), focus=False, radius=0.13 * u)
        if glows:
            self.content[0].insert(at, ("glows", glows, x, y, x + w, y + h))
        return h

    def _preview_card(self, y):
        p, s, x0, x1 = self.px, self.store.s, self.cx0, self.cx1
        pad = p(20)
        kw = x1 - x0 - 2 * pad
        m = self.model()
        kh = kw / (m.width + 0.64) * (m.height + 0.64)
        h = pad + p(36) + p(14) + kh + pad
        self._card(y, h)
        self.T(tr("live_preview"), self.fonts["h2"], MenuPainter.TEXT, x0 + pad, y + pad, x1, y + pad + p(36))
        bx = self._button("show", x1 - pad, y + pad + p(1), tr("show_keyboard"), "secondary", icon="light")
        tx = bx - p(28) - p(42)
        self._toggle("enabled", tx, y + pad + p(7), s["enabled"])
        lw = self.tw(tr("clock"), self.fonts["body"])
        self.T(tr("clock"), self.fonts["body"], MenuPainter.TEXT, tx - p(12) - lw, y + pad, tx - p(12), y + pad + p(36))
        ky = y + pad + p(50)
        self._keyboard(x0 + pad, ky, kw, self.live_frame())
        self.preview_rect = (int(x0 + pad - p(8)), int(ky - p(8)), int(x0 + pad + kw + p(8)), int(ky + kh + p(8)))
        return y + h

    # ---- layout
    def compose(self):
        p, (W, H) = self.px, self.size
        self.widgets, self.side, self.content, self.preview_rect = [], ([], []), ([], []), None
        self.sw = p(264)
        self.cx0 = self.sw + p(8)
        self.cx1 = max(self.cx0 + p(380), min(W - p(36), self.cx0 + p(860)))
        self._sidebar()
        y = getattr(self, "_page_" + self.page)(p(30) - self.scroll)
        self._nav("quit", p(14), H - p(18) - p(38), self.sw - p(28), "quit", tr("app_quit"), False, quiet=True)
        self.max_scroll = max(0, y + self.scroll + p(36) - H)
        if self.scroll > self.max_scroll:
            self.scroll = self.max_scroll
            return self.compose()
        if self.focus_visible:
            w = next((w for w in self.widgets if w["id"] == self.focus), None)
            if w:
                x0, y0, x1, y1 = w["rect"]
                r = w.get("radius", p(8)) + p(3)
                self.S("outline", 0xFFFFFF, x0 - p(3), y0 - p(3), x1 - x0 + p(6), y1 - y0 + p(6), r, max(1.5, p(2)), 225,
                       side=w["side"])

    def _sidebar(self):
        p = self.px
        x, w = p(14), self.sw - p(28)
        y = p(22)
        self.I(self.icon, x + p(8), y, p(32), side=True)
        self.T(APP, self.fonts["name"], MenuPainter.TEXT, x + p(52), y - p(3), x + w, y + p(19), side=True)
        self.T(f"v{__version__}", self.painter.f_small, MenuPainter.MUTED, x + p(52), y + p(18), x + w, y + p(36),
               side=True)
        y += p(58)
        text, color = self._status()
        self.S("round", 0x1A1B21, x + p(2), y, w - p(4), p(34), p(17), side=True)
        self.S("outline", 0x24262E, x + p(2), y, w - p(4), p(34), p(17), max(1.0, self.k), side=True)
        self.S("circle", color, x + p(16), y + p(13), p(8), side=True)
        self.T(text, self.painter.f_small, MenuPainter.ICON, x + p(32), y, x + w - p(10), y + p(34), 0x8000, side=True)
        y += p(52)
        for page, icon, key in self.PAGES:
            self._nav("nav:" + page, x, y, w, icon, tr(key), self.page == page)
            y += p(42)

    # ---- pages
    def _page_clock(self, y):
        p, s, x0, x1 = self.px, self.store.s, self.cx0, self.cx1
        d = s["display"]
        y = self._header(y, tr("nav_clock"), tr("clock_sub"))
        y = self._preview_card(y) + p(24)
        y = self._label(y, tr("display"))
        modes, gap, th = Tray.MODES, p(10), p(84)
        w = (x1 - x0 - gap * (len(modes) - 1)) / len(modes)
        for i, m in enumerate(modes):
            self._mode_tile("mode:" + m, x0 + i * (w + gap), y, w, th, self.MODE_ICONS[m], tr("mode_" + m), d["mode"] == m)
        y += th + p(12)
        pad, at, top = p(20), len(self.content[0]), y
        labels = ("screen_secs", "transition", "scroll_text", "scroll_speed")
        cx = x0 + pad + max(self.tw(tr(k), self.fonts["body"]) for k in labels) + p(24)
        y += p(12)
        rh = p(52)
        if d["mode"] != "scroll":
            self._field_label(tr("screen_secs"), y, rh, cx)
            self._slider("secs", cx + p(12), x1 - p(120), y + rh / 2, (d["secs"] - 1) / 9 * 100)
            self._value(f"{d['secs']:g} s", y, rh)
            y += rh
            self._field_label(tr("transition"), y, rh, cx)
            self._segmented("tr", cx, x1 - pad, y + (rh - p(40)) / 2,
                            [(t, None, tr("tr_" + t)) for t in TRANSITIONS], d["transition"])
            y += rh
        if d["mode"] in ("scroll", "mixed"):
            if d["mode"] == "scroll":
                self._field_label(tr("scroll_text"), y, rh, cx)
                name = next((tr(k) for t, k in self.TEXTS if t == d["scroll_text"]), d["scroll_text"])
                self._picker("pick:text", cx, y + (rh - p(36)) / 2, min(p(420), x1 - pad - cx), name, glyph="edit")
                y += rh
            self._field_label(tr("scroll_speed"), y, rh, cx)
            self._slider("speed", cx + p(12), x1 - p(120), y + rh / 2, (d["scroll_speed"] - 1) / 14 * 100)
            self._value(f"{d['scroll_speed']:g}", y, rh)
            y += rh + p(4)
            self._sep(y)
            y = self._toggle_row("smooth", y, "flow", tr("scroll_smooth"), tr("scroll_smooth_desc"), d["scroll_smooth"])
        y += p(8)
        self._card_behind(at, top, y - top)
        y += p(24)
        y = self._label(y, tr("formats"))
        top, at = y, len(self.content[0])
        y = self._toggle_row("hour12", y, "clock", tr("hour12"), None, d["hour12"])
        self._sep(y)
        y = self._toggle_row("zero", y, "clock", tr("leading_zero"), tr("leading_zero_desc"), d["leading_zero"])
        self._sep(y)
        y += p(12)
        self._field_label(tr("seconds"), y, p(40), cx)
        self._segmented("sec", cx, x1 - pad, y, [(v, None, tr("sec_" + v)) for v in SECONDS_STYLES], d["seconds"])
        y += p(40) + p(14)
        self._card_behind(at, top, y - top)
        return y

    def _hsv(self, color):
        h, sat, _ = color_hsv(color)
        if self.hue_memo and self.hue_memo[0] == color:
            h = self.hue_memo[1]
        return h, sat

    def _color_rows(self, y, color, pad, prefix=""):
        p, x0, x1 = self.px, self.cx0, self.cx1
        d, n = p(28), len(SWATCHES)
        gap = min(p(14), max(p(6), (x1 - x0 - 2 * pad - n * d) / (n - 1)))
        for i, c in enumerate(SWATCHES):
            self._swatch(f"{prefix}swatch:{i}", x0 + pad + i * (d + gap), y, d, c, c == color)
        y += d + p(22)
        h, sat = self._hsv(color)
        lw = max(self.tw(tr("color_hue"), self.fonts["body"]), self.tw(tr("color_sat"), self.fonts["body"])) + p(20)
        for wid, label, value, track, knob in (
                (prefix + "hue", tr("color_hue"), h / 3.6, [hsv_color(a * 60, 1) for a in range(7)], hsv_color(h, 1)),
                (prefix + "sat", tr("color_sat"), sat * 100, [0xFFFFFF, hsv_color(h, 1)], color)):
            self.T(label, self.fonts["body"], MenuPainter.ICON, x0 + pad, y, x0 + pad + lw, y + p(28), 0x8000)
            self._slider(wid, x0 + pad + lw + p(12), x1 - pad - p(12), y + p(14), value, track=track, knob=knob)
            y += p(42)
        return y - p(14)

    def _theme_tile(self, wid, x, y, w, h, stops, title, selected):
        p = self.px
        hov = self.hover == wid
        self.S("round", 0x1D1A30 if selected else (self.HOVER if hov else self.CARD), x, y, w, h, p(10))
        self.S("outline", MenuPainter.ACCENT if selected else self.LINE, x, y, w, h, p(10),
               max(1.5, p(2)) if selected else max(1.0, self.k))
        self.S("hgrad", stops, x + p(14), y + p(14), w - p(28), p(18), p(9))
        self.T(title, self.fonts["body"], MenuPainter.TEXT, x + p(12), y + p(38), x + w - p(12), y + h - p(8), 0x1 | 0x8000)
        self.add(wid, "tile", (x, y, x + w, y + h), radius=p(10))

    def _page_look(self, y):
        p, s, x0, x1 = self.px, self.store.s, self.cx0, self.cx1
        lo = s["look"]
        y = self._header(y, tr("nav_look"), tr("look_sub"))
        y = self._preview_card(y) + p(24)
        y = self._label(y, tr("themes"))
        names, cols, gap, th = list(THEMES), 4, p(10), p(72)
        w = (x1 - x0 - gap * (cols - 1)) / cols
        for i, name in enumerate(names):
            r, c = divmod(i, cols)
            self._theme_tile("theme:" + name, x0 + c * (w + gap), y + r * (th + gap), w, th, theme_stops(name),
                             tr("theme_" + name), lo["theme"] == name)
        y += ((len(names) + cols - 1) // cols) * (th + gap) - gap + p(24)
        y = self._label(y, tr("colors"))
        pad, at, top = p(20), len(self.content[0]), y
        y += pad
        style = lo["style"]
        lw = self.tw(tr("style"), self.fonts["body"]) + p(24)
        stops = [cint(c) for c in lo["gradient"]]
        kw = {"solid": dict(swatch=cint(lo["colors"]["hours"])), "gradient": dict(stops=stops), "flow": dict(stops=stops),
              "rainbow": dict(stops=[hsv_color(a * 60, 1) for a in range(6)]),
              "daytime": dict(stops=[cint(c) for _, c in DAYTIME[1:-1]]),
              "digits": dict(stops=[cint(c) for c in lo["digit_colors"]])}[style]
        self._field_label(tr("style"), y, p(36), x0 + pad + lw)
        self._picker("pick:style", x0 + pad + lw, y, min(p(340), x1 - pad - x0 - pad - lw), tr("style_" + style), **kw)
        y += p(36) + p(20)
        if style == "solid":
            self._segmented("role", x0 + pad, x1 - pad, y, [(r, None, tr("role_" + r)) for r in ROLES], self.role)
            y += p(40) + p(20)
            y = self._color_rows(y, cint(lo["colors"][self.role]), pad)
        elif style == "digits":
            self._segmented("dside", x0 + pad, x1 - pad, y,
                            [(0, None, tr("digit_left")), (1, None, tr("digit_right"))], self.digit_side)
            y += p(40) + p(20)
            y = self._color_rows(y, cint(lo["digit_colors"][self.digit_side]), pad)
        elif style in ("gradient", "flow"):
            self.stop_sel = min(self.stop_sel, len(stops) - 1)
            bs = p(36)
            bx = x1 - pad - bs
            self._icon_button("stop:del", bx, y, bs, "minus", enabled=len(stops) > 2)
            self._icon_button("stop:add", bx - p(8) - bs, y, bs, "add", enabled=len(stops) < 6)
            gx0, gx1 = x0 + pad, bx - p(8) - bs - p(16)
            self.S("hgrad", stops, gx0, y, gx1 - gx0, bs, p(9))
            dd = p(22)
            for i, c in enumerate(stops):
                cx_ = gx0 + p(18) + (gx1 - gx0 - p(36)) * i / (len(stops) - 1)
                on, wid = i == self.stop_sel, f"stop:{i}"
                ring = p(4) if on else (p(3) if self.hover == wid else p(2))
                self.S("circle", 0xFFFFFF if on or self.hover == wid else 0x15161A, cx_ - dd / 2, y + (bs - dd) / 2, dd)
                self.S("circle", c, cx_ - dd / 2 + ring, y + (bs - dd) / 2 + ring, dd - 2 * ring)
                self.add(wid, "swatch", (cx_ - dd / 2 - p(4), y, cx_ + dd / 2 + p(4), y + bs), radius=dd / 2 + p(4))
            y += bs + p(22)
            y = self._color_rows(y, stops[self.stop_sel], pad)
        else:
            text = tr("style_" + style + "_desc")
            th_ = self.wrap_h(text, self.fonts["body"], x1 - x0 - 2 * pad)
            self.W(text, self.fonts["body"], MenuPainter.ICON, x0 + pad, y, x1 - pad, y + th_)
            y += th_
        y += pad
        self._card_behind(at, top, y - top)
        y += p(24)
        y = self._label(y, tr("background"))
        bg = lo["background"]
        at, top = len(self.content[0]), y
        y += pad
        self._segmented("bg", x0 + pad, x1 - pad, y, [(b, None, tr("bg_" + b)) for b in BACKGROUNDS if b != "music"],
                        bg["mode"])
        y += p(40) + p(20)
        if bg["mode"] in ("dim", "breathe", "twinkle"):
            y = self._color_rows(y, cint(bg["color"]), pad, prefix="bg") + p(20)
        elif bg["mode"] == "gradient":
            text = tr("bg_gradient_desc")
            th_ = self.wrap_h(text, self.fonts["body"], x1 - x0 - 2 * pad)
            self.W(text, self.fonts["body"], MenuPainter.ICON, x0 + pad, y, x1 - pad, y + th_)
            y += th_ + p(20)
        if bg["mode"] != "off":
            lw = self.tw(tr("bg_level"), self.fonts["body"]) + p(24)
            self.T(tr("bg_level"), self.fonts["body"], MenuPainter.ICON, x0 + pad, y, x0 + pad + lw, y + p(28), 0x8000)
            self._slider("bg_level", x0 + pad + lw + p(12), x1 - p(120), y + p(14), bg["level"])
            self._value(f"{round(bg['level'])} %", y, p(28))
            y += p(28) + pad
        self._card_behind(at, top, y - top)
        y += p(24)
        y = self._label(y, tr("effects"))
        at, top = len(self.content[0]), y
        y += p(12)
        cx = x0 + pad + max(self.tw(tr("chime"), self.fonts["body"]), self.tw(tr("brightness"), self.fonts["body"])) + p(24)
        self._field_label(tr("chime"), y, p(40), cx)
        self._segmented("chime", cx, x1 - pad, y, [(c, None, tr("chime_" + c)) for c in CHIMES], lo["chime"])
        y += p(40) + p(12)
        self._field_label(tr("brightness"), y, p(52), cx)
        self._slider("brightness", cx + p(12), x1 - p(120), y + p(26), lo["brightness"])
        self._value(f"{round(lo['brightness'])} %", y, p(52))
        y += p(52) + p(8)
        self._card_behind(at, top, y - top)
        return y

    def _page_when(self, y):
        p, s, x0, x1 = self.px, self.store.s, self.cx0, self.cx1
        sh, ni = s["show"], s["night"]
        pad = p(20)
        y = self._header(y, tr("nav_when"), tr("when_sub"))
        at, top = len(self.content[0]), y
        y += p(12)
        cx = x0 + pad + max(self.tw(tr(k), self.fonts["body"]) for k in ("show_clock", "after")) + p(24)
        self._field_label(tr("show_clock"), y, p(40), cx)
        self._segmented("when", cx, x1 - pad, y, [(w, None, tr("when_" + w)) for w in WHEN], sh["when"])
        y += p(40) + p(12)
        if sh["when"] == "idle":
            self._field_label(tr("after"), y, p(36), cx)
            self._stepper("delay", x1 - pad, y, tr_secs(sh["delay"]))
            y += p(36) + p(12)
        self._card_behind(at, top, y - top)
        y += p(12)
        self._card(y, p(64) * 2)
        y = self._toggle_row("on_lock", y, "power", tr("on_lock"), tr("on_lock_desc"), sh["on_lock"])
        self._sep(y)
        y = self._toggle_row("hide_fs", y, "window", tr("hide_fullscreen"), tr("hide_fullscreen_desc"),
                             sh["hide_fullscreen"])
        y += p(12)
        rh = p(68)
        self._card(y, rh * 2)
        pw = p(220)
        hk = sh["hotkey"] if parse_hotkey(sh["hotkey"]) else ""
        self._picker("pick:hotkey", x1 - pad - pw, y + (rh - p(36)) / 2, pw, hk or tr("hotkey_none"), glyph="keyboard")
        self._row_text(y, rh, "keyboard", tr("hotkey"), tr("hotkey_desc"), right=x1 - pad - pw - p(16))
        y += rh
        self._sep(y)
        sx = self._stepper("off_after", x1 - pad, y + (rh - p(36)) / 2,
                           tr_secs(sh["off_after"] * 60) if sh["off_after"] else tr("never"))
        self._row_text(y, rh, "moon", tr("off_after"), tr("off_after_desc"), right=sx - p(16))
        y += rh + p(28)
        y = self._label(y, tr("night"))
        at, top = len(self.content[0]), y
        y = self._toggle_row("night", y, "moon", tr("night_hours"),
                             f"{ni['from']} – {ni['to']}" if ni["on"] else None, ni["on"])
        if ni["on"]:
            self._sep(y)
            y += p(14)
            self._field_label(tr("night_from"), y, p(36), x0 + pad + p(60))
            sx = self._stepper("night_to", x1 - pad, y, ni["to"])
            fx = self._stepper("night_from", sx - p(44), y, ni["from"])
            self.T(tr("night_to"), self.fonts["body"], MenuPainter.ICON, fx + self.tw("00:00", self.fonts["body"]) + p(90),
                   y, sx - p(8), y + p(36), 0x1)
            y += p(36) + p(14)
            cx = x0 + pad + max(self.tw(tr(k), self.fonts["body"]) for k in ("at_night", "night_brightness")) + p(24)
            self._field_label(tr("at_night"), y, p(40), cx)
            self._segmented("nact", cx, x1 - pad, y, [("dim", "sun", tr("night_dim")), ("red", None, tr("night_red")),
                                                      ("off", "power", tr("night_dark"))], ni["action"])
            y += p(40) + p(12)
            if ni["action"] != "off":
                self._field_label(tr("night_brightness"), y, p(52), cx)
                self._slider("night_bright", cx + p(12), x1 - p(120), y + p(26), ni["brightness"])
                self._value(f"{round(ni['brightness'])} %", y, p(52))
                y += p(52)
            y += p(8)
        self._card_behind(at, top, y - top)
        return y

    def _page_font(self, y):
        p, s, x0, x1 = self.px, self.store.s, self.cx0, self.cx1
        d = s["display"]
        pad = p(20)
        y = self._header(y, tr("nav_font"), tr("font_sub"))
        self._card(y, p(64))
        y = self._toggle_row("font_use", y, "font", tr("font_use"), tr("font_use_desc"), d["font"] == "custom") + p(12)
        at, top = len(self.content[0]), y
        y += pad
        lw = self.tw(tr("font_digit"), self.fonts["body"]) + p(24)
        self._field_label(tr("font_digit"), y, p(40), x0 + pad + lw)
        self._segmented("fd", x0 + pad + lw, x1 - pad, y, [(str(i), None, str(i)) for i in range(10)], self.font_digit)
        y += p(40) + p(14)
        sw_ = min(p(260), (x1 - x0) / 3)
        self._segmented("fside", x0 + pad, x0 + pad + sw_, y,
                        [(0, None, tr("font_left")), (1, None, tr("font_right"))], self.font_side)
        bx = self._button("font:copy", x1 - pad, y + p(3), tr("font_copy"), "secondary")
        self._button("font:reset", bx - p(10), y + p(3), tr("font_reset"), "quiet")
        y += p(40) + p(14)
        hint = tr("font_hint")
        hh = self.wrap_h(hint, self.painter.f_small, x1 - x0 - 2 * pad)
        self.W(hint, self.painter.f_small, MenuPainter.MUTED, x0 + pad, y, x1 - pad, y + hh)
        y += hh + p(14)
        m = self.model()
        y += self._keyboard(x0 + pad, y, x1 - x0 - 2 * pad, self.font_frame(), area=set(digit_area(m, self.font_side)))
        y += p(16)
        bx = self._button("font:show", x1 - pad, y, tr("show_keyboard"), "primary", icon="light")
        self._button("font:reset_all", bx - p(10), y, tr("font_reset_all"), "quiet")
        y += p(34) + pad
        self._card_behind(at, top, y - top)
        return y

    def _page_keyboard(self, y):
        p, s, x0, x1 = self.px, self.store.s, self.cx0, self.cx1
        pad, rh = p(20), p(68)
        y = self._header(y, tr("nav_keyboard"), tr("keyboard_sub"))
        ok = logitech_dll() is not None
        at, top = len(self.content[0]), y
        status = (tr("kb_ok"), MenuPainter.GREEN) if ok else (tr("kb_missing"), MenuPainter.AMBER)
        sw_ = self.tw(status[0], self.painter.f_small) + p(30)
        self.S("circle", status[1], x1 - pad - sw_, y + rh / 2 - p(4), p(8))
        self.T(status[0], self.painter.f_small, status[1], x1 - pad - sw_ + p(16), y, x1 - pad, y + rh)
        self._row_text(y, rh, "keyboard", tr("kb_ghub"), None, right=x1 - pad - sw_ - p(12))
        y += rh
        th_ = self.wrap_h(tr("kb_help"), self.fonts["body"], x1 - x0 - 2 * pad)
        self.W(tr("kb_help"), self.fonts["body"], MenuPainter.ICON, x0 + pad, y, x1 - pad, y + th_)
        y += th_ + pad
        self._card_behind(at, top, y - top)
        y += p(24)
        y = self._label(y, tr("kb_layout"))
        self._card(y, rh * 2)
        pw = p(320)
        self._picker("pick:model", x1 - pad - pw, y + (rh - p(36)) / 2, pw, tr("model_" + s["keyboard"]["model"]),
                     glyph="keyboard")
        self._row_text(y, rh, "keyboard", tr("kb_layout"), tr("model_" + self.model().name), right=x1 - pad - pw - p(16))
        y += rh
        self._sep(y)
        bx = self._button("kb:test", x1 - pad, y + (rh - p(34)) / 2, tr("kb_test_button"), "secondary", icon="light")
        self._row_text(y, rh, "light", tr("kb_test"), tr("kb_test_desc"), right=bx - p(16))
        y += rh + p(24)
        self._card(y, rh)
        self._row_text(y, rh, "apps", tr("kb_more"), tr("kb_more_desc"))
        return y + rh

    def _page_settings(self, y):
        p, s, t, c = self.px, self.store.s, self.tray, self.clock
        x1 = self.cx1
        y = self._header(y, tr("nav_settings"), tr("settings_sub"))
        rh = p(68)
        self._card(y, rh)
        y = self._toggle_row("autostart", y, "power", tr("start_windows"), tr("settings_start_desc"), t.autostart, rh)
        y += p(28)
        y = self._label(y, tr("settings_updates"))
        rows = 3 if c.new_version else 2
        self._card(y, rh * rows)
        ry = y
        if c.new_version:
            bx = self._button("update", x1 - p(20), ry + (rh - p(34)) / 2, tr("update_to", version=c.new_version),
                              "primary", icon="sync")
            self._row_text(ry, rh, "sync", tr("settings_new", version=c.new_version), None, right=bx - p(16),
                           icon_color=MenuPainter.ACCENT)
            ry += rh
            self._sep(ry)
        result = t._check_status()
        bx = self._button("check", x1 - p(20), ry + (rh - p(34)) / 2, tr("settings_check_now"), "secondary",
                          busy=t.checking)
        self._row_text(ry, rh, "sync", tr("updates"), result[0] if result else f"{APP} {__version__}",
                       right=bx - p(16), desc_color=result[1] if result else None)
        ry += rh
        self._sep(ry)
        self._toggle_row("auto_check", ry, "clock", tr("auto_check"), tr("settings_check_desc"), s["check_updates"], rh)
        y += rh * rows + p(28)
        y = self._label(y, tr("settings_lang"))
        self._card(y, rh)
        pw = p(230)
        name = next((n for code, n in self.LANG_NAMES if code == s["lang"]), None) or tr("lang_auto")
        self._picker("pick:lang", x1 - p(20) - pw, y + (rh - p(36)) / 2, pw, name, glyph="lang")
        self._row_text(y, rh, "lang", tr("settings_lang_label"), None, right=x1 - p(36) - pw)
        y += rh + p(28)
        y = self._label(y, tr("settings_help"))
        self._card(y, rh)
        bx = self._button("open:log", x1 - p(20), y + (rh - p(34)) / 2, tr("settings_open"), "secondary")
        self._row_text(y, rh, "doc", tr("open_log"), tr("settings_log_desc"), right=bx - p(16))
        return y + rh

    def _page_about(self, y):
        p, ic = self.px, MenuPainter.ICONS
        x0, x1 = self.cx0, self.cx1
        y += p(6)
        self.I(self.icon_big, x0, y, p(72))
        self.T(APP, self.fonts["hero"], MenuPainter.TEXT, x0 + p(92), y + p(4), x1, y + p(44))
        self.T(tr("about_version", version=__version__), self.painter.f_small, MenuPainter.MUTED, x0 + p(92),
               y + p(44), x1, y + p(64))
        y += p(72) + p(20)
        th = self.wrap_h(tr("about_tagline"), self.fonts["body"], x1 - x0)
        self.W(tr("about_tagline"), self.fonts["body"], MenuPainter.ICON, x0, y, x1, y + th)
        y += th + p(24)
        rows = (("link:star", "star", tr("star"), True), ("link:site", "globe", tr("about_site"), False),
                ("link:repo", "code", tr("about_source"), False), ("link:issues", "bug", tr("about_issue"), False),
                ("link:author", "person", tr("made_by", author=AUTHOR), False))
        rh = p(56)
        self._card(y, rh * len(rows))
        for i, (wid, icon, text, accent) in enumerate(rows):
            ry = y + i * rh
            if i:
                self._sep(ry)
            self._row_hover(wid, ry, rh)
            self._row_text(ry, rh, icon, text, None, right=x1 - p(52), icon_color=MenuPainter.ACCENT if accent else None)
            self.T(ic["link"], self.fonts["icon_s"], MenuPainter.MUTED, x1 - p(44), ry, x1 - p(20), ry + rh, 0x1)
            self.add(wid, "row", (x0, ry, x1, ry + rh), radius=p(10))
        y += rh * len(rows) + p(18)
        th = self.wrap_h(tr("about_license"), self.painter.f_small, x1 - x0)
        self.W(tr("about_license"), self.painter.f_small, MenuPainter.MUTED, x0 + p(4), y, x1, y + th)
        return y + th

    # ---- painting
    def draw(self, hdc, W, H, clip=None):
        """Composes and paints into hdc, W x H pixels (double-buffered; the page scrolls under the sidebar, clipped
        by painting it into its own buffer). clip (l, t, r, b): only that part changed (the live preview)."""
        self.size = (W, H)
        self.compose()
        if not self.bufs or self.bufs[0] != (W, H):  # kept from one paint to the next
            self._free_bufs()
            bufs = []
            for _ in range(2):
                mem = gdi32.CreateCompatibleDC(hdc)
                bmp = gdi32.CreateCompatibleBitmap(hdc, W, H)
                bufs.append((mem, bmp, gdi32.SelectObject(mem, bmp)))
            self.bufs, clip = ((W, H), bufs), None
        (side, _, _), (page, _, _) = self.bufs[1]
        l, t, r, b = clip or (0, 0, W, H)
        brush = gdi32.CreateSolidBrush(_cref(self.BG))
        for mem in (side, page):
            user32.FillRect(mem, byref(wt.RECT(l, t, r, b)), brush)
        gdi32.DeleteObject(brush)
        self._render(page, *self.content, clip=clip)
        x0 = max(l, self.sw)
        if r > x0:
            gdi32.BitBlt(side, x0, t, r - x0, b - t, page, x0, t, 0x00CC0020)
        self._render(side, *self.side, clip=clip)
        gdi32.BitBlt(hdc, l, t, r - l, b - t, side, l, t, 0x00CC0020)

    def _free_bufs(self):
        for mem, bmp, old in self.bufs[1] if self.bufs else ():
            gdi32.SelectObject(mem, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
        self.bufs = None

    def _render(self, hdc, shapes, texts, clip=None):
        gfx = Gfx(hdc, clip)
        for shape in shapes:
            gfx.draw(shape)
        gfx.close()
        if clip:
            gdi32.IntersectClipRect(hdc, *clip)
        self._texts(hdc, texts)
        if clip:
            gdi32.SelectClipRgn(hdc, None)

    def _texts(self, hdc, texts):
        gdi32.SetBkMode(hdc, 1)
        for item in texts:
            if item[0] == "text":
                _, text, font, color, l, t, r, b, flags = item
                self.painter._text(hdc, text, font, color, l, t, r, b, flags)
            elif item[0] == "wrap":
                _, text, font, color, l, t, r, b = item
                gdi32.SelectObject(hdc, font)
                gdi32.SetTextColor(hdc, _cref(color))
                rc = wt.RECT(int(l), int(t), int(r), int(b))
                user32.DrawTextW(hdc, text, -1, byref(rc), 0x10 | 0x800)  # WORDBREAK | NOPREFIX
            elif item[0] == "icon" and item[1]:
                _, hicon, x, y, size = item
                user32.DrawIconEx(hdc, int(x), int(y), hicon, int(size), int(size), 0, None, 3)

    # ---- actions
    def _widget(self, wid):
        return next((w for w in self.widgets if w["id"] == wid), None)

    def _hit(self, x, y):
        for w in self.widgets:
            x0, y0, x1, y1 = w["rect"]
            if (w["side"] or x >= self.sw) and x0 <= x < x1 and y0 <= y < y1:
                return w
        return None

    # ---- actions
    def _font_edit(self, change):
        """Applies change(font) to a complete copy of the font (missing digits taken from the built-in ones)."""
        s, m = self.store.s, self.model()
        base = classic_font(m)
        font = {ch: [list(v[0]), list(v[1])] for ch, v in s["display"]["custom_font"].items()} \
            if s["display"]["font"] == "custom" else {}
        for ch in "0123456789":
            font.setdefault(ch, [list(base[ch][0]), list(base[ch][1])])
        change(font, m)
        self.store.replace(merge(s, {"display": {"font": "custom", "custom_font": font}}))
        self._show_font(4)

    def _show_font(self, seconds):
        self.clock.show_for(seconds, lambda t: self.font_frame(Model(self.clock.model_name())))

    def activate(self, wid):
        st, s, t, c = self.store, self.store.s, self.tray, self.clock
        if wid.startswith("nav:"):
            self.page, self.scroll = wid[4:], 0
            if self.page == "settings":
                t.autostart = autostart_enabled()
            self._timers()
        elif wid == "enabled":
            st.set(("enabled",), not s["enabled"])
            t.refresh()
        elif wid == "show":
            c.show_for(15)
        elif wid.startswith("mode:"):
            st.set(("display", "mode"), wid[5:])
        elif wid.startswith("tr:"):
            st.set(("display", "transition"), wid[3:])
        elif wid.startswith("sec:"):
            st.set(("display", "seconds"), wid[4:])
        elif wid in ("hour12", "zero", "smooth"):
            key = {"hour12": "hour12", "zero": "leading_zero", "smooth": "scroll_smooth"}[wid]
            st.set(("display", key), not s["display"][key])
        elif wid.startswith("theme:"):
            st.replace(apply_theme(s, wid[6:]))
            self.stop_sel = 0
        elif wid.startswith("role:"):
            self.role = wid[5:]
        elif wid.startswith("dside:"):
            self.digit_side = int(wid[6:])
        elif wid.startswith(("swatch:", "bgswatch:")):
            bg = wid.startswith("bg")
            self.hue_memo = None
            self._set_color(SWATCHES[int(wid.split(":")[1])], bg, True)
        elif wid.startswith("stop:"):
            stops, i = [cint(x) for x in s["look"]["gradient"]], self.stop_sel
            if wid == "stop:add" and len(stops) < 6:
                j = min(i + 1, len(stops) - 1)
                mid = gradient_at((hex_color(color_hex(((stops[i] >> 16) & 255, (stops[i] >> 8) & 255, stops[i] & 255))),
                                   hex_color(color_hex(((stops[j] >> 16) & 255, (stops[j] >> 8) & 255, stops[j] & 255)))), 0.5)
                stops.insert(i + 1, cint(tuple(round(v) for v in mid)))
                self.stop_sel = i + 1
            elif wid == "stop:del" and len(stops) > 2:
                del stops[i]
                self.stop_sel = max(0, i - 1)
            elif wid[5:].isdigit():
                self.stop_sel = int(wid[5:])
            st.set(("look", "gradient"), ["#%06x" % v for v in stops])
        elif wid.startswith("bg:"):
            st.set(("look", "background", "mode"), wid[3:])
        elif wid.startswith("chime:"):
            st.set(("look", "chime"), wid[6:])
        elif wid.startswith("when:"):
            st.set(("show", "when"), wid[5:])
        elif wid.startswith("delay:"):
            cur = s["show"]["delay"]
            i = min(range(len(self.DELAYS)), key=lambda k: abs(self.DELAYS[k] - cur))
            i = max(0, min(len(self.DELAYS) - 1, i + (1 if wid.endswith("+") else -1)))
            st.set(("show", "delay"), self.DELAYS[i])
        elif wid.startswith("off_after:"):
            cur = s["show"]["off_after"]
            i = min(range(len(self.OFF_AFTER)), key=lambda k: abs(self.OFF_AFTER[k] - cur))
            i = max(0, min(len(self.OFF_AFTER) - 1, i + (1 if wid.endswith("+") else -1)))
            st.set(("show", "off_after"), self.OFF_AFTER[i])
        elif wid in ("on_lock", "hide_fs"):
            key = "on_lock" if wid == "on_lock" else "hide_fullscreen"
            st.set(("show", key), not s["show"][key])
        elif wid == "night":
            st.set(("night", "on"), not s["night"]["on"])
        elif wid.startswith(("night_from:", "night_to:")):
            name, step = wid.split(":")
            key = "from" if name == "night_from" else "to"
            v = (minutes_of(s["night"][key]) // 30 * 30 + (30 if step == "+" else -30)) % 1440
            other = minutes_of(s["night"]["to" if key == "from" else "from"])
            if v == other:
                v = (v + (30 if step == "+" else -30)) % 1440
            st.set(("night", key), f"{v // 60:02d}:{v % 60:02d}")
        elif wid.startswith("nact:"):
            st.set(("night", "action"), wid[5:])
        elif wid == "font_use":
            if s["display"]["font"] == "custom":
                st.set(("display", "font"), "classic")
            else:
                self._font_edit(lambda font, m: None)
        elif wid.startswith("fd:"):
            self.font_digit = wid[3:]
            self._show_font(4)
        elif wid.startswith("fside:"):
            self.font_side = int(wid[6:])
        elif wid.startswith("key:"):
            key, d, side = wid[4:], self.font_digit, self.font_side

            def toggle(font, m):
                keys = font[d][side]
                keys.remove(key) if key in keys else keys.append(key)

            self._font_edit(toggle)
        elif wid == "font:reset":
            d, side = self.font_digit, self.font_side
            self._font_edit(lambda font, m: font[d].__setitem__(side, list(classic_keys(m, d, side))))
        elif wid == "font:copy":
            d, a = self.font_digit, self.font_side
            b = 1 - a

            def copy(font, m):
                shift = DIGIT_ANCHOR[b] - DIGIT_ANCHOR[a]
                area, out = set(digit_area(m, b)), []
                for k in font[d][a]:
                    if k in F_KEYS[a]:
                        out.append(F_KEYS[b][F_KEYS[a].index(k)])
                        continue
                    cx, cy = m.center[k]
                    row = min(range(len(ROW_YS)), key=lambda r: abs(ROW_YS[r] + 0.5 - cy))
                    k2 = m.key_at(row, cx + shift)
                    if k2 in area:
                        out.append(k2)
                font[d][b] = out

            self._font_edit(copy)
        elif wid == "font:reset_all":
            st.replace(merge(s, {"display": {"font": "classic", "custom_font": {}}}))
        elif wid == "font:show":
            self._show_font(10)
        elif wid == "kb:test":
            m = Model(c.model_name())
            c.show_for(8.5, lambda t, m=m: self.font_frame(m, str(int(t / 0.85) % 10)))
        elif wid == "autostart":
            set_autostart(not t.autostart, t.argv)
            t.autostart = autostart_enabled()
        elif wid == "auto_check":
            st.set(("check_updates",), not s["check_updates"])
        elif wid == "check":
            t.check_now()
            self._timers()
        elif wid == "update":
            t.start_update()
        elif wid == "open:log":
            os.startfile(LOG_PATH)
        elif wid.startswith("link:"):
            os.startfile({"star": REPO_URL, "repo": REPO_URL, "site": SITE_URL, "issues": REPO_URL + "/issues",
                          "author": AUTHOR_URL}[wid[5:]])
        elif wid == "quit":
            k32.SetEvent(t.stop.h)
        elif wid.startswith("pick:"):
            self._pick(wid[5:])
        self.invalidate()

    def _edited_path(self, bg):
        lo = self.store.s["look"]
        if bg:
            return ("look", "background", "color"), lo["background"]["color"]
        if lo["style"] == "digits":
            return ("look", "digit_colors", self.digit_side), lo["digit_colors"][self.digit_side]
        if lo["style"] in ("gradient", "flow"):
            i = min(self.stop_sel, len(lo["gradient"]) - 1)
            return ("look", "gradient", i), lo["gradient"][i]
        return ("look", "colors", self.role), lo["colors"][self.role]

    def _set_color(self, color, bg, save):
        path, _ = self._edited_path(bg)
        self.store.set(path, "#%06x" % color, save)

    def _slide(self, x, save=False):
        wid = self.drag or self.focus
        w = next((w for w in self.widgets if w["id"] == wid), None)
        if not w or w["kind"] != "slider":
            return
        f = max(0.0, min(1.0, (x - w["x0"]) / max(1, w["x1"] - w["x0"]))) if x is not None else None
        self._slider_set(wid, f, save)
        self.invalidate()

    def _slider_set(self, wid, f, save, step=None):
        st, s = self.store, self.store.s
        if wid == "secs":
            cur = s["display"]["secs"]
            v = cur if f is None else round((1 + f * 9) * 2) / 2
            if step:
                v = max(1.0, min(10.0, cur + step * 0.5))
            st.set(("display", "secs"), v, save)
        elif wid == "speed":
            cur = s["display"]["scroll_speed"]
            v = cur if f is None else round(1 + f * 14)
            if step:
                v = max(1, min(15, round(cur) + step))
            st.set(("display", "scroll_speed"), v, save)
        elif wid in ("brightness", "bg_level", "night_bright"):
            path = {"brightness": ("look", "brightness"), "bg_level": ("look", "background", "level"),
                    "night_bright": ("night", "brightness")}[wid]
            lo = 0 if wid == "bg_level" else 5
            cur = st.get(path)
            v = cur if f is None else max(lo, round(f * 20) * 5)
            if step:
                v = max(lo, min(100, round(cur / 5) * 5 + step * 5))
            st.set(path, v, save)
        elif wid in ("hue", "sat", "bghue", "bgsat"):
            bg = wid.startswith("bg")
            color = cint(self._edited_path(bg)[1])
            h, sat = self._hsv(color)
            if wid.endswith("hue"):
                h = h if f is None else f * 360.0
                if step:
                    h = (h + step * 5) % 360
                sat = sat if sat > 0.05 else 1.0
            else:
                sat = sat if f is None else f
                if step:
                    sat = max(0.0, min(1.0, sat + step * 0.05))
            new = hsv_color(h, sat)
            self.hue_memo = (new, h)
            self._set_color(new, bg, save)

    def _pick(self, which):
        w = next((w for w in self.widgets if w["id"] == "pick:" + which), None)
        if not w:
            return
        st, s = self.store, self.store.s
        items = []

        def radio(text, value, checked, **kw):
            items.append(dict(kind="radio", text=text, value=value, checked=checked, **kw))

        if which == "text":
            for text, key in self.TEXTS:
                radio(tr(key), text, s["display"]["scroll_text"] == text)
            items.append(dict(kind="sep"))
            custom = all(s["display"]["scroll_text"] != t for t, _ in self.TEXTS)
            radio(tr("text_custom"), "custom", custom, icon="edit")
        elif which == "style":
            lo = s["look"]
            for style in STYLES:
                kw = {"solid": dict(swatch=cint(lo["colors"]["hours"])),
                      "rainbow": dict(stops=[hsv_color(a * 60, 1) for a in range(6)]),
                      "daytime": dict(stops=[cint(c) for _, c in DAYTIME[1:-1]]),
                      "digits": dict(stops=[cint(c) for c in lo["digit_colors"]])}.get(
                    style, dict(stops=[cint(c) for c in lo["gradient"]]))
                radio(tr("style_" + style), style, lo["style"] == style, **kw)
        elif which == "hotkey":
            for hk in self.HOTKEYS:
                radio(hk or tr("hotkey_none"), hk, (s["show"]["hotkey"] if parse_hotkey(s["show"]["hotkey"]) else "") == hk)
        elif which == "model":
            for name in ("auto",) + MODELS:
                radio(tr("model_" + name), name, s["keyboard"]["model"] == name)
        elif which == "lang":
            for code, name in self.LANG_NAMES:
                radio(name or tr("lang_auto"), code, s["lang"] == code)
        for it in items:
            it["min"] = (w["rect"][2] - w["rect"][0]) / self.k
        chosen = self._menu(items, w["rect"])
        if chosen is None or chosen.get("value") is None:
            return
        value = chosen["value"]
        if which == "text":
            if value == "custom":
                value = InputDialog(self.hwnd, self.k).ask(tr("text_dialog"), tr("text_prompt"), tr("text_hint"),
                                                           s["display"]["scroll_text"])
                if not value or not value.strip():
                    return
            st.set(("display", "scroll_text"), value)
        elif which == "style":
            st.set(("look", "style"), value)
        elif which == "hotkey":
            st.set(("show", "hotkey"), value)
        elif which == "model":
            st.set(("keyboard", "model"), value)
        elif which == "lang":
            st.set(("lang",), value)
            set_lang(value or detect_lang())
            self.tray.refresh()
        self.invalidate()

    def _menu(self, items, rect):
        """An owner-drawn popup menu in the panel's style, under a picker (entries with "items" open a submenu):
        the entry chosen, or None."""
        flat = []

        def build(entries):
            menu = user32.CreatePopupMenu()
            info = MENUINFO()
            info.cbSize, info.fMask, info.hbrBack = sizeof(info), 0x2, self.painter.bg_brush  # MIM_BACKGROUND
            user32.SetMenuInfo(menu, byref(info))
            for pos, it in enumerate(entries):
                i = len(flat)
                flat.append(it)
                if it.get("items"):
                    sub = build(it["items"])
                    user32.AppendMenuW(menu, 0x10 | 0x100, sub, ctypes.c_void_p(i))  # MF_POPUP | MF_OWNERDRAW
                elif it["kind"] in ("sep", "label"):  # a separator the keyboard skips, drawn like the rest
                    mii = MENUITEMINFOW()
                    mii.cbSize, mii.fMask = sizeof(mii), 0x100 | 0x20  # MIIM_FTYPE | MIIM_DATA
                    mii.fType, mii.dwItemData = 0x800 | 0x100, i  # MFT_SEPARATOR | MFT_OWNERDRAW
                    user32.InsertMenuItemW(menu, pos, True, byref(mii))
                else:
                    user32.AppendMenuW(menu, 0x100, i + 1, ctypes.c_void_p(i))  # MF_OWNERDRAW
            return menu

        menu = build(items)
        self.menu_items = flat
        pt = wt.POINT(int(rect[0]), int(rect[3]) + self.px(4))
        user32.ClientToScreen(self.hwnd, byref(pt))
        cmd = user32.TrackPopupMenu(menu, 0x0100 | 0x0080, pt.x, pt.y, 0, self.hwnd, None)  # RETURNCMD, NONOTIFY
        user32.DestroyMenu(menu)  # and its submenus
        self.menu_items = []
        return flat[cmd - 1] if cmd and cmd - 1 < len(flat) else None

    def _key(self, vk):
        order = []
        for w in self.widgets:
            if w["focus"] and w["id"] not in order:
                order.append(w["id"])
        if vk == 0x09:  # Tab, Shift+Tab
            self.focus_visible = True
            if order:
                i = order.index(self.focus) if self.focus in order else -1
                back = user32.GetKeyState(0x10) & 0x8000
                self.focus = order[(i + (-1 if back else 1)) % len(order)]
                self._reveal(self.focus)
            self.invalidate()
            return 0
        if vk in (0x0D, 0x20) and self.focus in order:  # Enter, Space
            self.activate(self.focus)
            return 0
        if vk in (0x25, 0x26, 0x27, 0x28) and self.focus in self.SLIDERS:  # arrows
            self._slider_set(self.focus, None, True, step=1 if vk in (0x26, 0x27) else -1)
            self.invalidate()
            return 0
        if vk in (0x21, 0x22, 0x24, 0x23):  # Page up/down, Home, End
            H = self.size[1]
            self.scroll_by({0x21: -H * 0.8, 0x22: H * 0.8, 0x24: -1e9, 0x23: 1e9}[vk])
            return 0
        return None

    def _reveal(self, wid):
        w = self._widget(wid)
        if not w or w["side"]:
            return
        p, H = self.px, self.size[1]
        if w["rect"][1] < p(16):
            self.scroll_by(w["rect"][1] - p(16))
        elif w["rect"][3] > H - p(16):
            self.scroll_by(w["rect"][3] - (H - p(16)))

    def scroll_by(self, dy):
        new = int(max(0, min(self.max_scroll, self.scroll + dy)))
        if new != self.scroll:
            self.scroll = new
            self.invalidate()

    # ---- window procedure
    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            r = self._on(hwnd, msg, wparam, lparam)
            if r is not None:
                return r
        except Exception as e:  # never let a drawing error take the tray down
            log(f"App window: {e!r}")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on(self, hwnd, msg, wparam, lparam):
        xy = lambda: (ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value)
        if msg == 0x000F and self.painter:  # WM_PAINT
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, byref(ps))
            rc, pr = wt.RECT(), ps.rcPaint
            user32.GetClientRect(hwnd, byref(rc))
            if rc.right > 0 and rc.bottom > 0:
                part = (pr.left, pr.top, pr.right, pr.bottom)
                self.draw(hdc, rc.right, rc.bottom, None if part == (0, 0, rc.right, rc.bottom) else part)
            user32.EndPaint(hwnd, byref(ps))
            return 0
        if msg == 0x0014:  # WM_ERASEBKGND: painted in WM_PAINT
            return 1
        if msg == 0x0005:  # WM_SIZE
            self._timers()
            self.invalidate()
            return 0
        if msg == 0x0024 and self.painter:  # WM_GETMINMAXINFO
            mmi = MINMAXINFO.from_address(lparam)
            mmi.ptMinTrackSize.x, mmi.ptMinTrackSize.y = self.px(self.MIN[0]), self.px(self.MIN[1])
            return 0
        if msg == 0x02E0:  # WM_DPICHANGED: another screen, or its scale changed
            self.set_scale((wparam & 0xFFFF) / 96.0)
            rc = wt.RECT.from_address(lparam)
            user32.SetWindowPos(hwnd, None, rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top, 0x0014)
            self.invalidate()
            return 0
        if msg == 0x0113:  # WM_TIMER
            if wparam == 1:
                r = self.preview_rect
                if r and r[3] > r[1]:
                    user32.InvalidateRect(hwnd, byref(wt.RECT(*r)), False)  # only the preview moves
                return 0
            if wparam == 3 and not self.tray.checking:
                user32.KillTimer(hwnd, 3)
            self.invalidate()
            return 0
        if msg == 0x0200:  # WM_MOUSEMOVE
            x, y = xy()
            if self.drag:
                self._slide(x)
                return 0
            w = self._hit(x, y)
            wid = w["id"] if w else None
            if wid != self.hover:
                self.hover = wid
                self.invalidate()
            if not self.tracking:
                tme = TRACKMOUSEEVENT(sizeof(TRACKMOUSEEVENT), 0x2, hwnd, 0)  # TME_LEAVE
                self.tracking = bool(user32.TrackMouseEvent(byref(tme)))
            return 0
        if msg == 0x02A3:  # WM_MOUSELEAVE
            self.tracking = False
            if self.hover:
                self.hover = None
                self.invalidate()
            return 0
        if msg == 0x0201:  # WM_LBUTTONDOWN
            x, y = xy()
            w = self._hit(x, y)
            self.pressed, self.focus_visible = (w["id"] if w else None), False
            if w and w["kind"] == "slider":
                self.drag = w["id"]
                self.focus = w["id"]
                user32.SetCapture(hwnd)
                self._slide(x)
            self.invalidate()
            return 0
        if msg == 0x0202:  # WM_LBUTTONUP
            x, y = xy()
            if self.drag:
                self._slide(x, save=True)
                self.drag = self.pressed = None
                user32.ReleaseCapture()
                return 0
            w, pressed = self._hit(x, y), self.pressed
            self.pressed = None
            if w and w["id"] == pressed:
                if w["focus"]:
                    self.focus = w["id"]
                self.activate(w["id"])
            self.invalidate()
            return 0
        if msg == 0x0215 and self.drag:  # WM_CAPTURECHANGED: dragging ended elsewhere
            wid, self.drag = self.drag, None
            self._slider_set(wid, None, True)
            return 0
        if msg == 0x020A:  # WM_MOUSEWHEEL
            self.scroll_by(-ctypes.c_short((wparam >> 16) & 0xFFFF).value / 120 * self.px(72))
            return 0
        if msg == 0x0100:  # WM_KEYDOWN
            return self._key(wparam)
        if msg == 0x002C and self.painter:  # WM_MEASUREITEM: a picker's menu
            mis = MEASUREITEMSTRUCT.from_address(lparam)
            if mis.CtlType == 1 and mis.itemData < len(self.menu_items):
                self.painter.measure(mis, self.menu_items[mis.itemData])
                return 1
        if msg == 0x002B and self.painter:  # WM_DRAWITEM
            dis = DRAWITEMSTRUCT.from_address(lparam)
            if dis.CtlType == 1 and dis.itemData < len(self.menu_items):
                self.painter.draw(dis, self.menu_items[dis.itemData])
                return 1
        if msg == 0x0121 and wparam == 2 and self.painter:  # WM_ENTERIDLE from the menu: dark rounded border
            self.painter.style_window(lparam)
        if msg == 0x0010:  # WM_CLOSE: the window goes, the app stays
            user32.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:  # WM_DESTROY
            for timer in (1, 2, 3):
                user32.KillTimer(hwnd, timer)
            self.hwnd, self.hover, self.pressed, self.drag = None, None, None, None
            self._free_bufs()
            self._free_gdi()
            self.tray.app_closed()
            return 0
        return None


def render_window_png(path, page, w=1060, h=1400, scale=1.0, settings=None):
    """Draws the window's page into a PNG (no window on screen): for checks and the website's pictures."""
    class _Stop:
        h = None

        def wait(self, s):
            return True

    clock = Clock(_Stop())
    if settings is not None:
        clock.apply(settings)

    class _Tray:
        pass

    t = _Tray()
    t.clock, t.store, t.autostart, t.checking, t.check_result, t.check_time = clock, Store(clock), False, False, None, 0
    t.stop, t.argv = _Stop(), []
    t.status = lambda: Tray.status(t)
    t._check_status = lambda: None
    app = AppWindow(t)
    app.set_scale(scale)
    app.page = page
    bmi = BITMAPINFOHEADER(sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    mem = gdi32.CreateCompatibleDC(None)
    dib = gdi32.CreateDIBSection(mem, byref(bmi), 0, byref(bits), None, 0)
    old = gdi32.SelectObject(mem, dib)
    app.draw(mem, w, h)
    gdi32.GdiFlush()
    raw = ctypes.string_at(bits, w * h * 4)
    canvas = Canvas(w, h)
    rgb = bytearray(w * h * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = raw[2::4], raw[1::4], raw[0::4]
    canvas.px = rgb
    canvas.save(path)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(dib)
    gdi32.DeleteDC(mem)
    app._free_bufs()
    app._free_gdi()
    return app


def run_with_tray(args, stop, clock, argv):
    try:
        tray = Tray(clock, stop, argv)
    except OSError as e:
        log(f"No icon next to the clock ({e}): running without it.")
        return clock.run()
    clock.notify = lambda: user32.PostMessageW(tray.hwnd, Tray.WM_SYNC, 0, 0)
    errors = []

    def worker():
        try:
            clock.run()
        except Exception as e:
            errors.append(e)
            log(f"Error: {e!r}")
        finally:
            tray.close_from_thread()

    t = threading.Thread(target=worker, name="keyboard-clock-engine", daemon=True)
    tray.worker = t
    t.start()
    threading.Thread(target=update_checker, name="keyboard-clock-update", daemon=True,
                     args=(clock, stop, lambda: user32.PostMessageW(tray.hwnd, Tray.WM_UPDATE, 0, 0))).start()
    if not (args.from_autostart or args.after_update):
        tray.open_app()
    tray.loop()
    k32.SetEvent(stop.h)
    t.join(5)
    for icon in tray.icons:
        user32.DestroyIcon(icon)
    if errors:
        raise errors[0]


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="keyboard_clock", description=f"{APP}: the time on your RGB keyboard.")
    p.add_argument("--stop", action="store_true", help="stop the clock running in the background")
    p.add_argument("--demo", action="store_true", help="play every display mode and look on the keyboard")
    p.add_argument("--preview", nargs="?", const="preview.png", metavar="FILE.png",
                   help="draw the demo scenes into a picture")
    p.add_argument("--bench", action="store_true", help="measure how fast the keyboard takes colors")
    p.add_argument("--delay", type=float, metavar="SECONDS", help="idle time before the clock shows (this run only)")
    p.add_argument("--mode", choices=DISPLAY_MODES[:-1], help="what the keyboard shows (this run only)")
    p.add_argument("--theme", choices=tuple(THEMES), help="colors and background (this run only)")
    p.add_argument("--model", choices=MODELS, help="keyboard layout (this run only)")
    p.add_argument("--lang", choices=LANGS, help="language of the app")
    p.add_argument("--no-tray", action="store_true", help="no icon next to the clock, no window: the clock only")
    p.add_argument("--install", action="store_true", help="start with Windows and add to the Start menu")
    p.add_argument("--uninstall", action="store_true", help="stop, remove from startup and the Start menu")
    p.add_argument("--autostart", choices=("on", "off"), help="start with Windows, or not")
    p.add_argument("--check-updates", choices=("on", "off"), help="check GitHub for new versions once a day")
    p.add_argument("--background", action="store_true", help="start without opening the window")
    p.add_argument("--from-autostart", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--after-update", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--screenshot", nargs=2, metavar=("PAGE", "FILE.png"), help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version=f"{APP} {__version__}")
    return p.parse_args(argv)


def _other_quit(stop, tries=100):
    """Waits for the running instance to quit, then takes its single-instance slot."""
    for _ in range(tries):
        k32.CloseHandle(stop.h)
        time.sleep(0.1)
        stop = StopSignal()
        if not stop.already_running:
            break
    return stop


def main(argv=None):
    args = parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")      # the Windows console can't show every character
    base = load_settings()
    set_lang(args.lang or base["lang"] or detect_lang())
    try:                                              # leftover of an in-place update
        os.remove((sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)) + ".old")
    except OSError:
        pass
    if args.stop:
        print("Stopped." if request_stop() else f"{APP} is not running.")
        return 0
    if args.uninstall:
        cmd_uninstall()
        return 0
    if args.check_updates:
        save_settings(clean_settings(merge(base, {"check_updates": args.check_updates == "on"})))
        print("Update checks on." if args.check_updates == "on" else "Update checks off.")
        if not (args.install or args.autostart):
            return 0
    if args.install:
        cmd_install([])
        return 0
    if args.autostart:
        set_autostart(args.autostart == "on")
        print("Starts with Windows." if args.autostart == "on" else "Does not start with Windows.")
        return 0
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))     # per-monitor v2
    except AttributeError:
        user32.SetProcessDPIAware()

    overrides = {}
    if args.theme:
        overrides["look"] = apply_theme(base, args.theme)["look"]
    if args.delay is not None:
        overrides.setdefault("show", {})["delay"] = args.delay
    if args.mode:
        overrides.setdefault("display", {})["mode"] = args.mode
    if args.model:
        overrides.setdefault("keyboard", {})["model"] = args.model
    if args.lang:
        overrides["lang"] = args.lang
    session = clean_settings(merge(base, overrides))
    lang = session["lang"] or detect_lang()

    if args.screenshot:
        render_window_png(args.screenshot[1], args.screenshot[0], settings=session)
        print(f"Saved: {os.path.abspath(args.screenshot[1])}")
        return 0
    if args.preview:
        save_preview(args.preview, preview_scenes(session, dt.datetime.now().replace(hour=13, minute=37, second=21)))
        print(f"Preview saved: {os.path.abspath(args.preview)}")
        return 0
    if args.bench:
        return run_bench()

    stop = StopSignal()
    if args.demo:
        try:
            return run_demo(stop, session, lang)
        except KeyboardInterrupt:
            return 0
        except Unsupported as e:
            print(e)
            return 1
    if stop.already_running and args.after_update:
        stop = _other_quit(stop)
    if stop.already_running:
        tray = user32.FindWindowW("KeyboardClockTray", None)
        if tray and not args.no_tray:                 # launched again: the running one opens its window
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(tray, byref(pid))
            user32.AllowSetForegroundWindow(pid.value)
            user32.PostMessageW(tray, Tray.WM_OPEN_APP, 0, 0)
            return 0
        msg = tr("already")
        if sys.stdout is None:
            user32.MessageBoxW(None, msg, APP, 0x40)
        else:
            print(msg + " (keyboard_clock.py --stop to quit it)")
        return 1
    if args.background or sys.stdout is None:
        k32.FreeConsole()
        sys.stdout = sys.stderr = None
    sys.unraisablehook = lambda u: log(f"Error: {u.exc_value!r} in {getattr(u.object, '__qualname__', u.object)!r}")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        os.replace(LOG_PATH, LOG_PATH.replace(".log", ".previous.log"))
    except OSError:
        pass
    clock = Clock(stop, overrides)
    log(f"{APP} {__version__}: started.")
    try:
        if args.no_tray:
            clock.run()
        else:
            run_with_tray(args, stop, clock, [])
    except KeyboardInterrupt:
        pass
    return 0


# =============================================================================
# Embedded UI font: Inter (https://rsms.me/inter), SIL Open Font License 1.1, subset (from Glowback).
# License: licenses/Inter-OFL.txt
# =============================================================================
INTER_FONTS = (
    (
        "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"
        "f2Vh/zL/LTGGqFfeUfNmoqk/nfBLYr4PBQsAMcqx9rRU+vXcCPBiB5ou7e0jXa02/I2Z/ecx+6s+f9KZxv9ZwzodkRkdLN8nf6vl"
        "Kmony9taE+du1fM8Li3nTq+GtC/TLn5peOm1xP98t4L2rYG+L7xK03a077OoLdYascdRYumEfnfiFx920mexb8qt7VbVM54f4b5g"
        "pGo7tPzkb8igUC2H1Hb4eo01WyHVXoI52raOI79gFj+RL2yhLXY5qqb8ot4koP9Ln85nxL8fZbffaVGt1f4nPexkh0bcPW9frt0O"
        "zZ+tyn/hM/i/0t9aYufJWlR5teN6+K/Gns6qvL8fOajWZsqPlOX8fWRF9wkQnKf+Lc7/eZ9b/rNZxNf+xzr2D3Yf/42Z+881U7Pm"
        "3+NMiCjaWd+/tQ7gm/+Fnv/jnfX/YN374J9rmKa0/m6r//dtyv9rn39l3dk55VzlMiFWVi4jV8J3pyWXqb7bl2iLsju/7/I8Sn+K"
        "ADvoaTtL8vC/0PMS9P+7T8e9n//hKrb9fnJA29pfvUvVIO4CNPyt9cP/l6Tf+Z5GmzVP+5d2Z56Qu2gqOwpWXGP3X/nTX9Sf9Q8b"
        "9n/OvkOkxtrBv9N1mX8HOpEUQ2xJ3Z/WGHadrjk678n/YH8b1s9VdH9VvYZ7yQiy/j/1kmL9q/9vWD9y5/u/PHkY8BOY/mfApWgN"
        "nMlz6RWoBp1Ee9Fp9BAdR9+jx+g++gU9Qd+h39Dv6BF6hhToB2yMjdFP2BSbop+xOTZHv9Dnf59gJ9wb/Yrd8RCkwMPgkOERcGhh"
        "P+yPtcmTv1gXh+BQrI/D8UTcBU/CiVBzKk7FNjgdZ0H9HDwX98bz4ZDjDXgT9sLV+AAeTJ72xcNxPW7A5B3Ly+kzz+R3mLpIhvTg"
        "MEL6AJbIGKI6DplCz2T0WejeyAY5ICvkCocFpPrBtzvyQFrIE8mhnBdEO93QSBQCtULhkKExcDiiMDg4FI6igF40Go8M0QQUC21M"
        "QtOgbgocDvSXBHZoBhzmKA3NBC4y0WxoORvNBR7nweGM5qMlwOtSOHzQMvHp/7XA1zo4vNF6tAn1QJvRVii/DW1H2mgH2omc0C60"
        "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"
        "Yd2EdRPWTVg3Yd2EdH9PYye7D81emX1k9rHZZ+V1r1eI5Bb7fQY040hbhD2/EtbiWNuGnFtv+rqeYyHHlImFnBtybsi5inMV5yqT"
        "G3LJIZcccskhlxxyySGXHHLJIZcccsmKS1ZcsuKSFZesuGTFJSsuWXHJisKvqUfqzT40+2x6aNJDkx6adGXSlUnPliPpSGJcSCm7"
        "yVLZT1bKauRvvWyQT8mZcq5cKJfKVXK93CJ3y33ykHxfHpen5Tl5UV6zXLyClVnl1mCrxhpjRdZEa6o1x2q1FuMVdY210dpu7bHe"
        "sY5YH1gnrTPWeeuyLezALrb72APsofYoe5w9wZ5sz7CfsxfYS+yV9jp7s73L3msftN+zj9mn7E/sC/ZVx3YyTk+nvzPIGe7UOcpp"
        "dKY4s5wWZ5GzzFntbHC2Oe3O285h56hzwvnY+dS55Fx3fbfI7eVWuFVurTvWTdxJ7jS32Z3vtrkr3LXuJneH+6Z7wH3X/dD9yD3r"
        "fuZe8aTXzSv1+nmVXrU32qv3GrynvJneXG+ht9Rb5a33tni7vX3eIe9977h32jvnXfSu+a5f6Jf55f5gv8Yf40f+RH+qP8dv9Rf7"
        "y/01/kZ/u7/Hf8c/4n/gn/TP+Of9y3hzD1LFqT6pAamhqVGpcakJqcmpGannUgtSS1IrU+tSm1O7UntTB1PvpY6lTqU+SV1IXQ3s"
        "IBP0DPoHg4LhQV2ggsZgSjAraAkWBkuCFcGaYEOwJdgVvBm8ExwO3g+OBR8FZ4JPg4vB1bRMB+midFm6f7oyPTRdmx6TVumG9OT0"
        "tPScdEt6YXpJekV6TXp9elN6G+xgju1gju1gjuViEcdijiUmFrJuyLoh64asG7JuyLqKdRXrKtZVrKtYV7FuxLoR60asG7FuxLoR"
        "68asG7NuzLox68asG7NuwroJ6yasm7BuwrqJ0Q0Z55BxDhnnkHEOGeeQcQ4Z55BxDhnnkHEOGeeQcQ4Z55BxDhnnkHEOGeeQcQ4Z"
        "55BxDhnnkHEOGeeQcQ4Z55BxDhnnkHEOGeeQcQ4Z55BxDhnnkHEOGeeQcVaMs2KcFeOsGGfFOCvGWTHOinFWjLNinBXjrBhnxTgr"
        "xlkxzopxVoyzYpwV46wYZ8U4K8ZZMc6KcVaMs2KcFeOsGGfFOCvGWTHOinFWjLNinBXjrBjniHGOGOeIcY4Y54hxjhjniHGOGOeI"
        "cY4Y54hxjhjniHGOGOeIcY4Y54hxjhjniHGOGOeIcY4Y54hxjhjniHGOGOeIcY4Y54hxjhjniHGOGOeIcY4Y54hxjhjnmHGOGeeY"
        "cY4Z55hxjhnnmHGOGeeYcY4Z55hxjhnnmHGOGeeYcY4Z55hxjhnnmHGOGeeYcY4Z55hxjhnnmHGOGeeYcY4Z55hxjhnnmHGOGeeY"
        "cY4Z55hxjhnnhHFOGOeEcU4Y54RxThjnhHFOGOeEcU4Y54RxThjnhHFOGOeEcU4Y54RxThjnhHFOGOeEcU4Y54RxThjnhHFOGOeE"
        "cU4Y54RxThjnhHFOGOeEcU4Y54RxTii8bmaxr5tZ7OtmFpvdR2Yfm31WPjTyoZEPjXxo5EMjHxp5ZeSVkVdGXhl5ZeSVkY+MfGTk"
        "IyMfGfnIyEdGPjbysZGPjXxs5GMjHxv5xMgnRj4x8omRT4x8Fh9JUpJkJOVISPRKiZlXZa8pT8NsWmOyRUb0EYNFHa0tSfGUPC8g"
        "qBbCHDeLajwu5+NR8qjIffE0m6JofQlIAg0C3QudazP0y+i1IHhar+fAOi3xlfmz9TdURTfYTmXobV45sJjWeCIxEwbAOJgAk6FZ"
        "eKJQlIn+ohJcUYU24VYsfzqGafrbxbT/De2nw2YsbQP8Drevkc/PWaG/53IJNhm539KKRhHan1WiVozNs0IXi2VilViHduh20S72"
        "iQPwJteSi80xsSZOazJpTSzXxHJNLNdEcn80bcjus8dN5ljn7zTnkN030b7JHOsS9PP7XbAHt2hLI0qF2e81U1ntpow/kHWt8d9M"
        "Z6pjv6NYFnNdxjTazjEpeyhlj9HzcbxMh9lY1jr4NWzHMeWSV+1qsUscEafRJi+DOrTDZ6IFvhb2wrvwEVyQvhwga2UiZ8hFciPa"
        "gQflMXlWXkL7r8yqsuqtJdZaa4d10DphXbBtuwxtu3p7qr3QXmPvtq+htdbqrHS2o4V23pVumVvtTnAXuqvRBjvsnvaqvLHeZLSz"
        "lnvt3rvexzQWAftUYk8todHo0qh6kkblKsoDMSsvp55yWk1OkpcTUs5kk1Odl6Mop87klOXlPEZjfxiMIg+aYu1XaueY4upVUH01"
        "yq50wpMwGaUs54BzQDyHctm3+ixhO7t0EE9h2lqT5jjrskHUY2qbSXWdtlwQQzF9jkn30MLloNtnN+RWY6Ga6qx36qnOQ1zncB2o"
        "znaus382UJ0buM5uuUB1Ls3VaV/qDFRnM9dZo+u0j9vHdZ2OzNVpH9aB6ryQq9Nuzwaq81SuTnt9LlCd73KdbZ2B6mznOvX32EEO"
        "wt8GPD6YvS7JXvhbIaTTQO+S6pQAfwsQkTqnTmzMpsFlTJvBvab7ej6mNGDOWZKQcoyYiSljMOU4pViySlaJRkyrwrTD2fOTvXTQ"
        "40TXC9kaHelmg6jEdBw1sN5cM/X3rD/DcfEZtNEV1RUt4lWMaW/kfmKH+AuOQf1l7BnkY7eA/LT+PTviYS/+xnF7dcoWLGkLVHdJ"
        "W4XXgVUY+nVJXYBXgQUUgi7pU4Wjn9rQk5uLeVicNHWdzEs7gmlDhbSu6hintmNqL2FZZ62zOm7SpXUUr6QA+qnDurzUfaKN/Adz"
        "sVz6JuLrCSxnk4lncyxrqbWUGHsgj7k6vdlqFsPxeBtqZ2O5nAarQX+LU6zIi2eZqe9AL2BcezG+IP4HPNECQ+AB8St6Jraanju9"
        "Cv8By8Ua+pb4ulyf0VtiuVJcGAkP42EE44WHd6fJIo3Xy7l4JdXPs4rxmvmWKCG5av3/xvFq8BjK6Sdnaby2zkK5VmhFuXV4FyvR"
        "LYZNkL2SLc8bjzYs1wHvTCBa8tId7TFLXrONdOXqzHFhYi5ge/W1qzPP088Ec4E84cs5VzNpJG2HUWsKofDm1pAn59WbWyPOmHBT"
        "a8R7HG5qjdidF25uzUO0HaFbgy1ZQv+JZk+X1jRT0N6yG7q0ptGERZi2pEtrajlMo7tDfmv65AU96qP83sZYjqGvih3wivgvHCG/"
        "hF/Ar5BlS/AeuB+WUXt/SNsHaczgNRDPW49oHuPiMAYQyGLa51K34RwE8E4GiERn6iqcp+kekDQj6WRbqf4vl5g6n3yHsy2U4nPx"
        "pX7AhuM5RZhNwDnNJPLpBNobZoga7IU68mmWFO+srwIDiJ70lkRFZ0/g7EnfxdbCf9LTvUvgGWSAPEcTUQ7PIhtG6e/yw0M4L3jY"
        "zDnHIy9m42ykCZpR4jl4HkfsPD2bgB2wE+cwv4fd8Adoh7fgDdgDf8Q5ksR+0P7GglgDxBqfWNONWNOdWFNCrCnNa8Mscb+4LvT/"
        "aAeQYIENDrjgQXfI6P8fAAU4nm+DYv1fBKAESuEOnL/4kIIA0jiPvBN6QW/oA32hH9wF/aEcfgAVcA/OPO+FShgId8MguA/0f1wN"
        "xCWNMrZuhAjwnOtEIfkLl5Kn8O3amxVnY9oLuAzbO1f0xvbOE/cRdkPMU1KfrrrFtB0k5PNzX1yI903x0jOzWvX/O5jd+nQzlqvH"
        "XBHOdWnmjbVlcvNtPFqNSQey9yc8erjz+fP/AZ4S7RE="
    ),
    (
        "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"
        "tnpa/awhlmeNtSZaM6zZ1kIaUVda66zN1g5rl7Xfes86Yp2wTlsXbbCTdq7dxe5m97YH2sPt0fZ4e4r9hD3PXmQvs1fbG+xt9pv2"
        "Hvsd+6B91P6Nfda+HLEjWZEOkaJIj0jfSEXEjYyJTIhMi1RHFkReiKyIrI1sitRGfhzZFzkQORw5Hvkocj5yNRqP5uiv2UdLo+XR"
        "odEgOi46KVoVnRutiS6Nroquj26Jvh59K/p29P3oB9GT0TPRSzEVaxXLjxXGSmJlsUGxEbHK2KOxqbFZsfmxxbHlsTWxjbHtsZ2x"
        "vbF3Y4dix2KnYudiV+LReJt4Qbw43jPeLz4k7sXHxifGZ8RnxxfGl8RXxtfFN8d3xHfF98ffix+Jn4ifjl+ki3sykZvokuiW6J0Y"
        "mBieGJ0Yn5iSeCIxL7EosSyxOrEhsS3xZmJP4p3EwcTRxG8SZxOXk3YyK9khWZTskeybrEi6yTHJCclpyerk/OSi5NLkyuTa5Mbk"
        "tuTryV3Jfcl3kweTHyRPJD9KnkteTqlUMpWTKkgVpUpSvVPlqSEpN1WZGp+alJqRqk7NTy1KLU2tTK1JrU9twi3CsS3CsS3CsTqf"
        "Jz5ffIHxOSLriKwjso7IOiLriKwrsq7IuiLriqwrsq7IeiLriawnsp7IeiLriawvsr7I+iLri6wvsr7IBiIbiGwgsoHIBiIbGFlH"
        "cHYEZ0dwdgRnR3B2BGdHcHYEZ0dwdgRnR3B2BGdHcHYEZ0dwdgRnR3B2BGdHcHYEZ0dwdgRnR3B2BGdHcHYEZ0dwdgRnR3B2BGdH"
        "cHYEZ0dwdgRnR3B2BGdXcHYFZ1dwdgVnV3B2BWdXcHYFZ1dwdgVnV3B2BWdXcHYFZ1dwdgVnV3B2BWdXcHYFZ1dwdgVnV3B2BWdX"
        "cHYFZ1dwdgVnV3B2BWdXcHYFZ1dwdgVnV3B2BWdPcPYEZ09w9gRnT3D2BGdPcPYEZ09w9gRnT3D2BGdPcPYEZ09w9gRnT3D2BGdP"
        "cPYEZ09w9gRnT3D2BGdPcPYEZ09w9gRnT3D2BGdPcPYEZ09w9gRnT3D2BGdfcPYFZ19w9gVnX3D2BWdfcPYFZ19w9gVnX3D2BWdf"
        "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"
        "+OD6e8//B6IgfJ0="
    ),
)


if __name__ == "__main__":
    sys.exit(main())
