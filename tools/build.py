"""Builds the README pictures and the website from the app itself (its layouts, digits, colors and window).

    python tools/build.py            # everything
    python tools/build.py --no-shots # skip the window screenshots (slower)

Writes:
  assets/banner.svg                      animated keyboard at the top of the README
  docs/img/window-<page>-<lang>.webp     the app's window, in each language
  docs/social-preview[-<lang>].png       1280x640 link previews (GitHub, Reddit, Discord, X…)
  docs/favicon.ico, docs/favicon.svg, docs/img/icon-*.png
  docs/[<lang>/]index.html               the website (GitHub Pages, served from /docs), from tools/page.html
  docs/sitemap.xml, docs/robots.txt, docs/llms.txt, docs/.nojekyll
Texts come from tools/i18n/<lang>.json. Needs Pillow (pip install pillow); the app itself does not.
"""
import datetime as dt
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import keyboard_clock as kc  # noqa: E402

from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
SITE = "https://ilyomix.github.io/keyboard-clock/"
REPO = "https://github.com/Ilyomix/keyboard-clock"
SETUP = REPO + "/releases/latest/download/KeyboardClockSetup.exe"
STORE = "https://apps.microsoft.com/detail/9N5M0SCJNPZ3"
# Microsoft's "Get it from Microsoft" badge in each language, and its text
STORE_BADGES = {"en": "en-us", "fr": "fr", "es": "es", "de": "de", "it": "it", "pt": "pt-br"}
STORE_ALTS = {"en": "Get it from Microsoft", "fr": "Obtenir sur le Microsoft Store", "es": "Obtener en Microsoft Store",
              "de": "Im Microsoft Store herunterladen", "it": "Scarica da Microsoft Store", "pt": "Baixar na Microsoft Store"}
GLOWBACK = "https://ilyomix.github.io/glowback/"
AUTHOR_URL = "https://ilyomix.github.io/"
ALL_LANGS = ["en", "fr", "es", "de", "it", "pt"]
LANGS = [l for l in ALL_LANGS if os.path.isfile(os.path.join(ROOT, "tools", "i18n", f"{l}.json"))]
LOCALES = {"en": "en_US", "fr": "fr_FR", "es": "es_ES", "de": "de_DE", "it": "it_IT", "pt": "pt_BR"}
NAMES = {"en": "English", "fr": "Français", "es": "Español", "de": "Deutsch", "it": "Italiano", "pt": "Português"}
MODEL = kc.Model("tkl-ansi")
HOURS, MINUTES = kc.hex_color("#ff5900"), kc.hex_color("#00ccff")
SECONDS = (222, 226, 236)
OFF, CASE, BG = (28, 30, 37), (13, 14, 18), (7, 8, 11)
SHOTS = (("clock", 1600, 660), ("look", 1600, 940), ("timer", 1180, 800), ("font", 1600, 560))


def hexc(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def digits(text):
    keys = []
    for pos, ch in enumerate(text):
        keys += kc.classic_keys(MODEL, ch, pos)
    return keys


def colon(what):
    """The colon's keys: after the hours ("hours") or before the minutes ("minutes"), as in the app."""
    return list(kc.COLON[what][0])


def box(x, y, w, h, scale, ox, oy):
    g = 0.07
    return ox + (x + g) * scale, oy + (y + g) * scale, (w - 2 * g) * scale, (h - 2 * g) * scale


# ---------------------------------------------------------------------------
# Animated banner (README)
# ---------------------------------------------------------------------------
def svg_keys(scale, ox, oy, keys=None, fill=None):
    out = []
    for k, x, y, w, h in MODEL.rects:
        if keys is not None and k not in keys:
            continue
        bx, by, bw, bh = box(x, y, w, h, scale, ox, oy)
        out.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="{0.13 * scale:.1f}"'
                   + (f' fill="{fill}"' if fill else "") + "/>")
    return "".join(out)


def banner_svg():
    scale, W, H = 60, 1280, 520
    ox, oy = (W - MODEL.width * scale) / 2, (H - MODEL.height * scale) / 2
    fade, hold = 0.5, 2.5
    half = 2 * fade + hold
    cyc = 2 * half
    pc = lambda t: f"{100 * t / cyc:.3f}%"
    css = [f".h{{animation:h {cyc:g}s ease-in-out infinite}}",
           f"@keyframes h{{0%{{opacity:0}}{pc(fade)}{{opacity:1}}{pc(fade + hold)}{{opacity:1}}{pc(half)}{{opacity:0}}100%{{opacity:0}}}}",
           f".m{{opacity:0;animation:m {cyc:g}s ease-in-out infinite}}",
           f"@keyframes m{{0%{{opacity:0}}{pc(half)}{{opacity:0}}{pc(half + fade)}{{opacity:1}}{pc(half + fade + hold)}{{opacity:1}}100%{{opacity:0}}}}"]
    n = len(kc.SECONDS_BLOCK)
    for i in range(n):
        a, b = 100 * i / n, min(99.4, 100 * (i + 1) / n)
        css.append(f".s{i}{{opacity:0;animation:s{i} 60s linear -21s infinite}}"
                   f"@keyframes s{i}{{0%{{opacity:0}}{a:.2f}%{{opacity:0}}{b:.2f}%{{opacity:1}}99.5%{{opacity:1}}100%{{opacity:0}}}}")
    css.append("@media (prefers-reduced-motion:reduce){.h,.m,[class^=s]{animation:none}.h{opacity:1}}")

    def layer(cls, keys, color):
        k = set(keys)
        return (f'<g class="{cls}"><g filter="url(#glow)" opacity=".85">{svg_keys(scale, ox, oy, k, hexc(color))}</g>'
                f"{svg_keys(scale, ox, oy, k, hexc(color))}</g>")

    p = 0.32 * scale
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
             'aria-label="Keyboard Clock: the time 13:37 drawn in big digits on the RGB keys of a keyboard">',
             "<title>Keyboard Clock: the time drawn on your RGB keyboard</title>",
             '<defs><filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="11"/></filter>'
             '<radialGradient id="ga" cx="22%" cy="18%" r="55%"><stop offset="0" stop-color="#ff5a00" stop-opacity=".22"/>'
             '<stop offset="1" stop-color="#ff5a00" stop-opacity="0"/></radialGradient>'
             '<radialGradient id="gb" cx="82%" cy="90%" r="55%"><stop offset="0" stop-color="#00c8ff" stop-opacity=".18"/>'
             '<stop offset="1" stop-color="#00c8ff" stop-opacity="0"/></radialGradient></defs>',
             f"<style>{''.join(css)}</style>",
             f'<rect width="{W}" height="{H}" rx="28" fill="{hexc(BG)}"/><rect width="{W}" height="{H}" rx="28" fill="url(#ga)"/>'
             f'<rect width="{W}" height="{H}" rx="28" fill="url(#gb)"/>',
             f'<rect x="{ox - p:.1f}" y="{oy - p:.1f}" width="{MODEL.width * scale + 2 * p:.1f}" height="{MODEL.height * scale + 2 * p:.1f}"'
             f' rx="{0.42 * scale:.1f}" fill="{hexc(CASE)}" stroke="#23262f" stroke-width="2"/>',
             f'<g fill="{hexc(OFF)}">{svg_keys(scale, ox, oy)}</g>',
             layer("h", digits("13") + colon("hours"), HOURS), layer("m", colon("minutes") + digits("37"), MINUTES)]
    for i, k in enumerate(kc.SECONDS_BLOCK):
        parts.append(layer(f"s{i}", [k], SECONDS))
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# PNG pictures
# ---------------------------------------------------------------------------
def font(size):
    return ImageFont.truetype(os.path.join(DOCS, "fonts", "space-grotesk-700.woff"), size)


def body_font(size):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def keyboard_png(scale, lit, ss=2):
    s = scale * ss
    pad = int(1.2 * s)
    w, h = int(MODEL.width * s) + 2 * pad, int(MODEL.height * s) + 2 * pad
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d, g = ImageDraw.Draw(base), ImageDraw.Draw(glow)
    cp = 0.32 * s
    d.rounded_rectangle((pad - cp, pad - cp, pad + MODEL.width * s + cp, pad + MODEL.height * s + cp), radius=0.42 * s,
                        fill=CASE + (255,), outline=(35, 38, 47, 255), width=max(1, ss))
    for k, x, y, kw, kh in MODEL.rects:
        bx, by, bw, bh = box(x, y, kw, kh, s, pad, pad)
        color = lit.get(k)
        d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=0.13 * s, fill=(color or OFF) + (255,))
        if color:
            g.rounded_rectangle((bx, by, bx + bw, by + bh), radius=0.13 * s, fill=color + (255,))
    glow = glow.filter(ImageFilter.GaussianBlur(0.42 * s))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(glow)
    out.alpha_composite(base)
    for k, x, y, kw, kh in MODEL.rects:
        if k in lit:
            bx, by, bw, bh = box(x, y, kw, kh, s, pad, pad)
            ImageDraw.Draw(out).rounded_rectangle((bx, by, bx + bw, by + bh), radius=0.13 * s, fill=lit[k] + (255,))
    return out.resize((w // ss, h // ss), Image.LANCZOS), pad // ss


def social_preview(path, title, subtitle):
    W, H = 1280, 640
    bg = Image.new("RGB", (W, H), BG)
    spots = Image.new("RGB", (W, H), (0, 0, 0))
    sd = ImageDraw.Draw(spots)
    sd.ellipse((-130, -240, 470, 360), fill=(255, 90, 0))
    sd.ellipse((830, 300, 1470, 940), fill=(0, 170, 230))
    img = Image.blend(bg, spots.filter(ImageFilter.GaussianBlur(128)), 0.45).convert("RGBA")
    lit = {k: HOURS for k in digits("13") + colon("hours")}
    lit.update({k: SECONDS for k in kc.SECONDS_BLOCK[:3]})
    kb, pad = keyboard_png(54, lit)
    img.alpha_composite(kb, ((W - kb.width) // 2, H - kb.height + pad - 30))
    d = ImageDraw.Draw(img)
    y = 44
    for line in title.split("\n"):
        d.text((64, y), line, font=font(58), fill=(240, 242, 247))
        y += 66
    d.text((66, y + 8), subtitle, font=body_font(25), fill=(165, 172, 188))
    img.convert("RGB").save(path, optimize=True)


def icon_png(size):
    bgra = kc.icon_pixels(size)
    return Image.frombuffer("RGBA", (size, size), bytes(bgra), "raw", "BGRA", 0, 1)


def icon_svg():
    cells = []
    for i in range(9):
        r, c = divmod(i, 3)
        if i < 6:
            t = i / 5
            color = tuple(round(HOURS[k] + (MINUTES[k] - HOURS[k]) * t) for k in range(3))
            op = 1
        elif i == 6:
            color, op = MINUTES, 0.55
        else:
            color, op = (120, 126, 140), 0.55
        cells.append(f'<rect x="{2 + c * 10:.1f}" y="{2 + r * 10:.1f}" width="8.4" height="8.4" rx="1.8" '
                     f'fill="{hexc(color)}" opacity="{op}"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">' + "".join(cells) + "</svg>"


SHOT_TIME = dt.datetime(2026, 11, 20, 13, 37, 21)


def _fixed_frame(self):
    """The window's live preview at 13:37:21, so every picture shows the same time."""
    return self.renderer().frame(1.2, SHOT_TIME, None, False)


def window_shot(page, lang, w, h):
    kc.set_lang(lang)
    kc.AppWindow.live_frame = _fixed_frame
    settings = kc.clean_settings({"show": {"when": "idle"}, "lang": lang,
                                  "alarms": [{"time": "07:30", "days": [0, 1, 2, 3, 4]}, {"time": "13:00", "on": False}]})
    tmp = os.path.join(DOCS, "img", f"_tmp_{page}_{lang}.png")
    kc.render_window_png(tmp, page, w=w, h=h, settings=settings, attrs={"font_digit": "8", "font_side": 1})
    out = os.path.join(DOCS, "img", f"window-{page}-{lang}.webp")
    Image.open(tmp).save(out, "WEBP", quality=88, method=6)
    os.remove(tmp)


# ---------------------------------------------------------------------------
# Website
# ---------------------------------------------------------------------------
ICONS = {
    "digits": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5" fill="currentColor"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 2-.8 2-1.8 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.2 0-1 .8-1.8 1.8-1.8H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8z"/><circle cx="7.5" cy="11" r="1.2" fill="currentColor"/><circle cx="10.5" cy="7.5" r="1.2" fill="currentColor"/><circle cx="15" cy="7.5" r="1.2" fill="currentColor"/>',
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 1.5M9 2h6"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "music": '<path d="M9 18V5l11-2v13"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
    "font": '<path d="M4 20 9 5h2l5 15M6 14h8"/><path d="M15 20l3-8 3 8"/>',
    "keyboard": '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7.5 14h9"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7.5a4 4 0 0 1 8 0V11"/>',
    "back": '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4.5v4h4"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
}


def svg_icon(name):
    return (f'<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def url_of(lang):
    return SITE if lang == LANGS[0] else f"{SITE}{lang}/"


def esc(s):
    """Escapes for text and double-quoted attributes, leaving apostrophes readable."""
    return html.escape(s, quote=False).replace('"', "&quot;")


def plain(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def load(lang):
    with open(os.path.join(ROOT, "tools", "i18n", f"{lang}.json"), encoding="utf-8") as f:
        text = f.read().replace("{REPO}", REPO).replace("{SETUP}", SETUP).replace("{SITE}", SITE)
    return json.loads(text)


def demo_svg(label):
    scale, p = 40, 0.32 * 40 + 2
    w, h = MODEL.width * scale + 2 * p, MODEL.height * scale + 2 * p
    lit = {k: HOURS for k in digits("13") + colon("hours")}
    keys = []
    for k, x, y, kw, kh in MODEL.rects:
        bx, by, bw, bh = box(x, y, kw, kh, scale, p, p)
        style = f' style="fill:{hexc(lit[k])}" filter="url(#kbglow)"' if k in lit else ""
        keys.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="{0.13 * scale:.1f}" '
                    f'data-k="{html.escape(k)}"{style}/>')
    return (f'<svg id="kb" class="kb" viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="{esc(label)}">'
            '<defs><filter id="kbglow" x="-60%" y="-60%" width="220%" height="220%">'
            '<feGaussianBlur in="SourceGraphic" stdDeviation="6" result="b"/>'
            '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
            f'<rect x="2" y="2" width="{w - 4:.1f}" height="{h - 4:.1f}" rx="{0.42 * scale:.1f}" fill="{hexc(CASE)}" '
            f'stroke="#23262f" stroke-width="1.5"/><g class="keys">{"".join(keys)}</g></svg>')


def page(lang, T, all_t, template):
    here = url_of(lang)
    root = "" if lang == LANGS[0] else "../"
    preview = SITE + ("social-preview.png" if lang == LANGS[0] else f"social-preview-{lang}.png")
    alternates = "".join(f'<link rel="alternate" hreflang="{l}" href="{url_of(l)}">' for l in LANGS)
    alternates += f'<link rel="alternate" hreflang="x-default" href="{SITE}">'
    og_alt = "".join(f'<meta property="og:locale:alternate" content="{LOCALES[l]}">' for l in LANGS if l != lang)
    app_ld = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "Keyboard Clock",
              "description": T["description"], "inLanguage": lang, "url": here, "image": preview,
              "screenshot": f"{SITE}img/window-clock-{lang}.webp", "applicationCategory": "UtilitiesApplication",
              "operatingSystem": "Windows 10, Windows 11", "softwareVersion": kc.__version__, "installUrl": STORE, "downloadUrl": SETUP,
              "softwareRequirements": "Logitech G HUB, Windows Dynamic Lighting or OpenRGB",
              "license": "https://opensource.org/licenses/MIT", "isAccessibleForFree": True,
              "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
              "author": {"@type": "Person", "name": "Ilyomix", "url": AUTHOR_URL}, "sameAs": [REPO]}
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": lang,
              "mainEntity": [{"@type": "Question", "name": plain(q["q"]),
                              "acceptedAnswer": {"@type": "Answer", "text": plain(q["a"])}} for q in T["faq"]]}
    ld = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    menu = "".join(f'<li><a href="{url_of(l)}" hreflang="{l}" lang="{l}" data-lang="{l}"'
                   f'{" aria-current=\"page\"" if l == lang else ""}>{NAMES[l]}<small>{l.upper()}</small></a></li>' for l in LANGS)
    steps = "".join(f'<li class="step"><span class="n">{i + 1}</span><h3>{s["t"]}</h3><p>{s["p"]}</p></li>'
                    for i, s in enumerate(T["steps"]))
    feats = "".join(f'<li class="feat"><span class="i">{svg_icon(f["i"])}</span><h3>{f["t"]}</h3><p>{f["p"]}</p></li>'
                    for f in T["features"])
    sizes = {name: (w, h) for name, w, h in SHOTS}
    shots = "".join(f'<figure class="shot{" on" if i == 0 else ""}" id="shot-{s["page"]}" role="tabpanel">'
                    f'<img src="{root}img/window-{s["page"]}-{lang}.webp" alt="{esc(s["alt"])}" '
                    f'loading="lazy" decoding="async" width="{sizes[s["page"]][0]}" height="{sizes[s["page"]][1]}">'
                    f'<figcaption>{s["caption"]}</figcaption></figure>' for i, s in enumerate(T["shots"]))
    tabs = "".join(f'<button type="button" role="tab" aria-controls="shot-{s["page"]}"><b>{s["tab"]}</b>'
                   f'<small>{s["caption"]}</small></button>' for s in T["shots"])
    install = "".join(f'<li class="step"><span class="n">{i + 1}</span><h3>{s["t"]}</h3><p>{s["p"]}</p></li>'
                      for i, s in enumerate(T["install_steps"]))
    install_more = "".join(f'<div class="card"><h3>{c["t"]}</h3><p>{c["p"]}</p>'
                           + (f'<code>{html.escape(c["code"])}</code>' if c.get("code") else "") + "</div>"
                           for c in T["install_more"])
    works = "".join(f'<span class="chip">{w}</span>' for w in T["works"])
    langs_foot = "".join(f'<a href="{url_of(l)}" hreflang="{l}" lang="{l}" data-lang="{l}"'
                         f'{" aria-current=\"page\"" if l == lang else ""}>{NAMES[l]}</a>' for l in LANGS)
    logo = icon_svg().replace("<svg ", '<svg aria-hidden="true" ', 1)
    yes = "".join(f"<li>{x}</li>" for x in T["compat_yes"])
    no = "".join(f"<li>{x}</li>" for x in T["compat_no"])
    faq = "".join(f'<details><summary><h3>{q["q"]}</h3></summary><p>{q["a"]}</p></details>' for q in T["faq"])
    themes = "".join(f'<button type="button" data-theme="{k}"{" aria-pressed=\"true\"" if k == "neon" else ""}>{v}</button>'
                     for k, v in T["demo_themes"].items())
    data = {"rects": [[k, x, y, w, h] for k, x, y, w, h in MODEL.rects],
            "font": {ch: [kc.classic_keys(MODEL, ch, 0), kc.classic_keys(MODEL, ch, 1)] for ch in "0123456789"},
            "colon": {"h": colon("hours"), "m": colon("minutes")},
            "seconds": list(kc.SECONDS_BLOCK), "off": OFF, "sec": SECONDS, "width": MODEL.width,
            "themes": {"neon": {"h": HOURS, "m": MINUTES}, "sunset": {"g": ["#ff2e63", "#ff8a00", "#ffd200"]},
                       "matrix": {"h": kc.hex_color("#00ff41"), "m": kc.hex_color("#00c832")}, "rainbow": {"r": 1}}}
    redirect = ""
    if lang == LANGS[0] and len(LANGS) > 1:
        redirect = ("<script>(function(){var A=" + json.dumps(LANGS[1:]) + ",go=function(c){location.replace(c+'/'+location.search+location.hash)};"
                    "try{var s=localStorage.getItem('kbclock-lang');if(s){if(A.indexOf(s)>=0)go(s);return}}catch(e){}"
                    "var L=navigator.languages&&navigator.languages.length?navigator.languages:[navigator.language||''];"
                    "for(var i=0;i<L.length;i++){var c=String(L[i]).slice(0,2).toLowerCase();if(c==='en')return;"
                    "if(A.indexOf(c)>=0){go(c);return}}})();</script>")
    values = dict(lang=lang, locale=LOCALES[lang], title=esc(T["title"]), description=esc(T["description"]),
                  og_title=esc(T["og_title"]), og_description=esc(T["og_description"]), here=here,
                  preview=preview, alternates=alternates, og_alt=og_alt, redirect=redirect, root=root,
                  app_ld=ld(app_ld), faq_ld=ld(faq_ld), langs_menu=menu, lang_code=lang.upper(), repo=REPO, setup=SETUP, store=STORE,
                  store_badge=f"https://get.microsoft.com/images/{STORE_BADGES[lang]}%20dark.svg", store_alt=STORE_ALTS[lang],
                  steps=steps, feats=feats, shots=shots, tabs=tabs, install=install, install_more=install_more,
                  works=works, langs_foot=langs_foot, logo=logo, yes=yes, no=no, faq=faq, themes=themes,
                  keyboard=demo_svg(T["demo_label"]), glowback=GLOWBACK, author=AUTHOR_URL, version=kc.__version__,
                  year=str(dt.date.today().year), data=json.dumps(data, separators=(",", ":")))
    for k, v in T.items():
        if isinstance(v, str):
            values.setdefault(k, v)
    out = template
    for _ in range(3):   # texts may hold {{version}}, {{setup}}…
        for k, v in values.items():
            out = out.replace("{{" + k + "}}", v)
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", out)))
    if missing:
        raise SystemExit(f"{lang}: no value for {missing}")
    return out


def write(rel, text):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    shots = "--no-shots" not in sys.argv
    os.makedirs(os.path.join(DOCS, "img"), exist_ok=True)
    write("assets/banner.svg", banner_svg())
    write("docs/favicon.svg", icon_svg())
    for size in (192, 512):
        icon_png(size).save(os.path.join(DOCS, "img", f"icon-{size}.png"), optimize=True)
    icon_png(256).save(os.path.join(DOCS, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    all_t = {l: load(l) for l in LANGS}
    with open(os.path.join(ROOT, "tools", "page.html"), encoding="utf-8") as f:
        template = f.read()
    for l in LANGS:
        T = all_t[l]
        name = "social-preview.png" if l == LANGS[0] else f"social-preview-{l}.png"
        social_preview(os.path.join(DOCS, name), T["preview_title"], T["preview_sub"])
        if shots:
            for page_, w, h in SHOTS:
                window_shot(page_, l, w, h)
        write("docs/index.html" if l == LANGS[0] else f"docs/{l}/index.html", page(l, T, all_t, template))
        print("built", l)
    today = dt.date.today().isoformat()
    alt = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{url_of(l)}"/>' for l in LANGS)
    alt += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{SITE}"/>'
    urls = "".join(f"\n  <url>\n    <loc>{url_of(l)}</loc>{alt}\n    <lastmod>{today}</lastmod>\n  </url>" for l in LANGS)
    write("docs/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{urls}\n</urlset>\n')
    write("docs/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n")
    T = all_t["en"]
    faq = "\n".join(f"- {plain(q['q'])} {plain(q['a'])}" for q in T["faq"])
    feats = "\n".join(f"- {plain(f['t'])}: {plain(f['p'])}" for f in T["features"])
    write("docs/llms.txt", f"# Keyboard Clock\n\n> {T['description']}\n\n- Website: {SITE}\n- Source code (MIT): {REPO}\n"
          f"- Download (Windows installer): {SETUP}\n- Version: {kc.__version__}\n\n## Features\n\n{feats}\n\n## FAQ\n\n{faq}\n")
    write("docs/.nojekyll", "")


if __name__ == "__main__":
    main()
