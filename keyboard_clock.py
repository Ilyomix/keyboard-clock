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
    "1": [("..#.", "...#"), "..#", "..#.", ".#..", "#.."],     # a single slash
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
                "leading_zero": True, "seconds": "block"},
    "look": {"theme": "neon", "style": "solid",
             "colors": {"hours": "#ff5900", "minutes": "#00ccff", "date": "#b36bff", "seconds": "#9a9a9a",
                        "text": "#ffffff"},
             "gradient": ["#ff5900", "#ff2e63", "#00ccff"], "digit_colors": ["#ff5900", "#00ccff"],
             "background": {"mode": "off", "color": "#1e2a78", "level": 25}, "chime": "hour", "brightness": 100},
    "night": {"on": False, "from": "22:00", "to": "07:00", "action": "dim", "brightness": 30},
    "keyboard": {"backend": "auto", "model": "auto"},
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


def digit_spans(model, text, role):
    spans = []
    for pos, ch in enumerate(text[:2]):
        for k in classic_keys(model, ch, pos):
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
        spans = digit_spans(self.model, self._digits(item["show"], wall), item["show"])
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
    """Watches idle time, lock, hotkey, full-screen apps and night hours, and drives the keyboard."""

    def __init__(self, stop, overrides=None, settings_path=SETTINGS_PATH):
        self.stop, self.path, self.overrides = stop, settings_path, overrides or {}
        self.settings = self._load()
        self.mtime = self._mtime()
        self.manual = False            # shown with the hotkey
        self.paused_until = 0.0
        self.status = "starting"
        self.last_frame = {}

    def _mtime(self):
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return 0.0

    def _load(self):
        s = load_settings(self.path)
        return clean_settings(merge(s, self.overrides)) if self.overrides else s

    def toggle(self):
        self.manual = not self.manual

    def run(self):
        s = self.settings
        lang = s["lang"] or detect_lang()
        model = Model(s["keyboard"]["model"] if s["keyboard"]["model"] != "auto" else default_model())
        renderer = Renderer(model, s, lang)
        backend = None
        holding = False
        shown_at = 0.0
        next_try = 0.0
        last_check = 0.0
        locked = full = apps_hit = False
        chime_at, chimed = None, None
        hotkey = None
        combo = parse_hotkey(s["show"]["hotkey"])
        if combo:
            hotkey = Hotkey(combo, self.toggle)
            hotkey.start()
        try:
            while True:
                now = time.monotonic()
                if now - last_check >= 1.0:                       # slower checks, once a second
                    last_check = now
                    m = self._mtime()
                    if m != self.mtime:
                        self.mtime, s = m, self._load()
                        self.settings = s
                        renderer.configure(s)
                        log("Settings reloaded.")
                    sh = s["show"]
                    locked = sh["on_lock"] and session_locked()
                    full = sh["hide_fullscreen"] and fullscreen_app()
                    apps_hit = bool(sh["hide_apps"]) and bool(running_exes() & set(sh["hide_apps"]))
                sh = s["show"]
                idle = idle_seconds()
                want = s["enabled"] and now >= self.paused_until and (
                    self.manual or sh["when"] == "always" or (sh["when"] == "idle" and idle >= sh["delay"])
                    or locked)
                if want and not locked and not self.manual and (full or apps_hit):
                    want = False
                if want and not holding and now >= next_try:
                    try:
                        backend = backend or open_backend(s)
                        holding = backend.open()
                    except (Unsupported, OSError) as e:
                        log(f"Keyboard not available: {e}")
                        holding = False
                    if holding:
                        shown_at, chime_at = now, None
                        self.status = "showing"
                    else:
                        next_try = now + 10
                        self.status = "waiting for the keyboard"
                elif not want and holding:
                    backend.release()
                    holding = False
                    self.status = "hidden"
                if holding:
                    wall = dt.datetime.now()
                    chime = s["look"]["chime"]
                    if chime != "off" and wall.second < 2 and (wall.minute == 0 or (chime == "half" and wall.minute == 30)):
                        stamp = (wall.hour, wall.minute)
                        if stamp != chimed and now - shown_at > 2:
                            chimed, chime_at = stamp, now
                    chime_u = None
                    if chime_at is not None:
                        chime_u = now - chime_at
                        if chime_u >= CHIME_SECS:
                            chime_at, chime_u, shown_at = None, None, now     # restart on the hours
                    night = night_now(s["night"], wall)
                    dark = (night and s["night"]["action"] == "off") or (
                        sh["off_after"] > 0 and not self.manual and now - shown_at > sh["off_after"] * 60)
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


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(prog="keyboard_clock", description="Shows the time on your RGB keyboard.")
    p.add_argument("--stop", action="store_true", help="stop the clock running in the background")
    p.add_argument("--demo", action="store_true", help="play every display mode and look on the keyboard")
    p.add_argument("--preview", nargs="?", const="preview.png", metavar="FILE.png",
                   help="draw the demo scenes into a picture")
    p.add_argument("--bench", action="store_true", help="measure how fast the keyboard takes colors")
    p.add_argument("--delay", type=float, metavar="SECONDS", help="idle time before the clock shows (this run only)")
    p.add_argument("--mode", choices=DISPLAY_MODES[:-1], help="what the keyboard shows (this run only)")
    p.add_argument("--theme", choices=tuple(THEMES), help="colors and background (this run only)")
    p.add_argument("--model", choices=MODELS, help="keyboard layout (this run only)")
    p.add_argument("--version", action="version", version=f"{APP} {__version__}")
    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")      # the Windows console can't show every character

    if args.stop:
        print("Stopped." if request_stop() else "Keyboard Clock is not running.")
        return 0
    base = load_settings()
    if args.theme:
        base = apply_theme(base, args.theme)
    overrides = {}
    if args.delay is not None:
        overrides.setdefault("show", {})["delay"] = args.delay
    if args.mode:
        overrides.setdefault("display", {})["mode"] = args.mode
    if args.model:
        overrides.setdefault("keyboard", {})["model"] = args.model
    base = clean_settings(merge(base, overrides))
    lang = base["lang"] or detect_lang()

    if args.preview:
        save_preview(args.preview, preview_scenes(base, dt.datetime.now().replace(hour=13, minute=37, second=21)))
        print(f"Preview saved: {os.path.abspath(args.preview)}")
        return 0
    if args.bench:
        return run_bench()

    stop = StopSignal()
    if stop.already_running and not args.demo:
        print("Keyboard Clock is already running. Use --stop to stop it.")
        return 1
    try:
        if args.demo:
            return run_demo(stop, base, lang)
        if args.theme:
            overrides["look"] = base["look"]
        log(f"{APP} {__version__}: the time shows after {base['show']['delay']:g} s without input. Ctrl+C to stop.")
        Clock(stop, overrides).run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Unsupported as e:
        log(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
