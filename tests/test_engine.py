"""Engine tests: run with `python -m unittest` from the repository root."""
import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import keyboard_clock as kc  # noqa: E402

WALL = dt.datetime(2026, 11, 20, 13, 37, 21)


class Layouts(unittest.TestCase):
    def test_every_key_has_codes(self):
        for name in kc.MODELS:
            for k in kc.Model(name).keys:
                self.assertIn(k, kc.KEY_CODES, f"{name}: {k}")

    def test_hid_usages_are_unique_per_model(self):
        for name in kc.MODELS:
            usages = [kc.KEY_CODES[k][0] for k in kc.Model(name).keys]
            self.assertEqual(len(usages), len(set(usages)), name)

    def test_rows_do_not_overlap(self):
        for name in kc.MODELS:
            m = kc.Model(name)
            for y in kc.ROW_YS:
                spans = sorted((x, x + w) for k, x, ky, w, h in m.rects if ky == y)
                for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
                    self.assertLessEqual(a1, b0 + 1e-9, f"{name} row {y}")


class Digits(unittest.TestCase):
    def test_every_digit_lands_on_keys_in_every_model(self):
        for name in kc.MODELS:
            m = kc.Model(name)
            for ch in "0123456789":
                for pos in (0, 1):
                    keys = kc.classic_keys(m, ch, pos)
                    self.assertTrue(keys, f"{name} {ch} {pos}")
                    self.assertEqual(len(keys), len(set(keys)))

    def test_left_and_right_digits_never_share_a_key(self):
        m = kc.Model("tkl-iso")
        for a in "0123456789":
            for b in "0123456789":
                self.assertFalse(set(kc.classic_keys(m, a, 0)) & set(kc.classic_keys(m, b, 1)), a + b)

    def test_digits_stay_between_f1_and_f8(self):
        m = kc.Model("tkl-iso")
        for ch in "0123456789":
            for pos in (0, 1):
                for k in kc.classic_keys(m, ch, pos):
                    self.assertLess(m.center[k][0], 11, f"{ch} {pos} {k}")

    def test_the_built_in_digits_are_the_drawn_ones(self):
        m = kc.Model("tkl-iso")
        for ch in "0123456789":
            for pos in (0, 1):
                self.assertEqual(kc.classic_keys(m, ch, pos), list(kc.DEFAULT_FONT[ch][pos]), f"{ch} {pos}")
                self.assertTrue(set(kc.DEFAULT_FONT[ch][pos]) <= set(kc.digit_area(m, pos)), f"{ch} {pos}")


class CustomFont(unittest.TestCase):
    def test_areas_are_disjoint_and_hold_the_classic_digits(self):
        for name in kc.MODELS:
            m = kc.Model(name)
            left, right = set(kc.digit_area(m, 0)), set(kc.digit_area(m, 1))
            self.assertFalse(left & right, name)
            for ch, (l, r) in kc.classic_font(m).items():
                self.assertTrue(set(l) <= left and set(r) <= right, f"{name} {ch}")

    def test_custom_digits_are_used_and_kept_in_their_area(self):
        m = kc.Model("tkl-iso")
        font = kc.classic_font(m)
        font["1"] = [["F2", "3", "E", "D", "X", "Y"], ["F6", "8", "U", "J", "M", "E"]]   # Y and E: wrong side
        s = kc.clean_settings({"display": {"font": "custom", "custom_font": font}})
        self.assertEqual(kc.font_keys(m, "1", 0, s["display"]["custom_font"]), ["F2", "3", "E", "D", "X"])
        self.assertEqual(kc.font_keys(m, "1", 1, s["display"]["custom_font"]), ["F6", "8", "U", "J", "M"])
        r = kc.Renderer(m, s)
        lit = {k for k, c in r.frame(r.tsecs + 1, WALL.replace(hour=11)).items()
               if sum(c) and k not in kc.SECONDS_BLOCK}
        self.assertEqual(lit, {"F2", "3", "E", "D", "X", "F6", "8", "U", "J", "M"})

    def test_classic_is_used_when_the_font_is_classic_or_a_digit_is_missing(self):
        m = kc.Model("tkl-iso")
        custom = kc.clean_font({"1": [["F1"], ["F5"]], "x": 3, "2": "junk"})
        self.assertEqual(list(custom), ["1"])
        self.assertEqual(kc.font_keys(m, "2", 0, custom), kc.classic_keys(m, "2", 0))
        s = kc.clean_settings({"display": {"font": "classic", "custom_font": {"1": [["F1"], ["F5"]]}}})
        self.assertIsNone(kc.Renderer(m, s).custom_font)


class Text(unittest.TestCase):
    def test_pixel_font_is_well_formed(self):
        for ch, g in kc.PIXEL.items():
            self.assertEqual(len(g), 5, ch)
            self.assertEqual(len(set(map(len, g))), 1, ch)
            self.assertTrue(set("".join(g)) <= {"#", "."}, ch)

    def test_accents_and_unknown_characters(self):
        cols = kc.text_columns([("Été ß ☃", "text")])
        self.assertTrue(cols)
        self.assertEqual(kc.plain_upper("Août"), "AOUT")


class Rendering(unittest.TestCase):
    def setUp(self):
        self.m = kc.Model("tkl-iso")
        self.s = kc.clean_settings({})

    def test_frames_cover_every_key_with_valid_colors(self):
        for theme in kc.THEMES:
            s = kc.apply_theme(self.s, theme)
            for mode in ("time", "time_date"):
                s2 = kc.clean_settings(kc.merge(s, {"display": {"mode": mode}}))
                r = kc.Renderer(self.m, s2)
                for t in (0.0, 0.3, 1.5, 3.2, 7.9):
                    f = r.frame(t, WALL)
                    self.assertEqual(set(f), set(self.m.keys))
                    for c in f.values():
                        self.assertTrue(all(0 <= v <= 255 and isinstance(v, int) for v in c))

    def test_hours_then_minutes(self):
        r = kc.Renderer(self.m, self.s)
        T, secs = r.tsecs, r.items[0]["secs"]
        lit = lambda t: {k for k, c in r.frame(t, WALL).items() if sum(c) > 0 and k not in kc.SECONDS_BLOCK}
        hours = set(kc.classic_keys(self.m, "1", 0) + kc.classic_keys(self.m, "3", 1))
        minutes = set(kc.classic_keys(self.m, "3", 0) + kc.classic_keys(self.m, "7", 1))
        self.assertEqual(lit(T + 1), hours)
        self.assertEqual(lit(secs + 3 * T + 1), minutes)
        self.assertEqual(lit(0.0), set())                       # fully faded at the very start

    def test_fade_is_gradual(self):
        r = kc.Renderer(self.m, self.s)
        level = lambda t: r.frame(t, WALL)["4"][0]
        self.assertLess(level(0.1), level(0.3))
        self.assertLess(level(0.3), level(1.0))

    def test_transitions(self):
        for tr in kc.TRANSITIONS:
            s = kc.clean_settings(kc.merge(self.s, {"display": {"transition": tr}}))
            r = kc.Renderer(self.m, s)
            mid = r.frame(r.tsecs / 2 if r.tsecs else 0.0, WALL)
            full = r.frame(r.tsecs + 1, WALL)
            self.assertGreater(sum(map(sum, full.values())), 0, tr)
            if tr != "none":
                self.assertNotEqual(mid, full, tr)

    def test_dissolve_keeps_part_of_the_keys_midway(self):
        s = kc.clean_settings(kc.merge(self.s, {"display": {"transition": "dissolve", "transition_secs": 0.8}}))
        r = kc.Renderer(self.m, s)
        dur = r.items[0]["secs"] + 2 * r.tsecs
        keys = kc.classic_keys(self.m, "1", 0) + kc.classic_keys(self.m, "3", 1)
        f = r.frame(dur - r.tsecs / 2, WALL)
        on = sum(1 for k in keys if sum(f[k]) > 0)
        self.assertTrue(0.2 * len(keys) <= on <= 0.8 * len(keys), on)

    def test_seconds_styles(self):
        for style in kc.SECONDS_STYLES:
            s = kc.clean_settings(kc.merge(self.s, {"display": {"seconds": style}}))
            for name in ("tkl-iso", "full-ansi"):
                kc.Renderer(kc.Model(name), s).frame(1.5, WALL)
        s = kc.clean_settings(kc.merge(self.s, {"display": {"seconds": "numpad"}}))
        f = kc.Renderer(kc.Model("full-iso"), s).frame(1.5, WALL)
        self.assertGreater(sum(f["KP2"]), 0)
        self.assertGreater(sum(f["KP1"]), 0)

    def test_night_and_dark(self):
        r = kc.Renderer(self.m, self.s)
        self.assertTrue(all(c == (0, 0, 0) for c in r.frame(1.5, WALL, dark=True).values()))
        s = kc.clean_settings(kc.merge(self.s, {"night": {"on": True, "action": "red"}}))
        f = kc.Renderer(self.m, s).frame(1.5, WALL, night=True)
        lit = [c for c in f.values() if sum(c)]
        self.assertTrue(lit and all(c[0] > c[1] and c[0] > c[2] for c in lit))

    def test_chime(self):
        f = kc.Renderer(self.m, self.s).frame(1.0, WALL, chime_u=0.9)
        self.assertGreater(sum(1 for c in f.values() if sum(c)), 5)


class _Stop:
    h = None

    def wait(self, s):
        return True


class Timers(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = kc.Clock(_Stop(), settings_path=os.path.join(self.dir.name, "settings.json"))

    def tearDown(self):
        self.dir.cleanup()

    def test_timer_counts_down_then_flashes_then_stops_on_input(self):
        c = self.clock
        c.start_timer(2)
        now = c.timer["end"] - 90
        v = c._timer_tick(now, idle=500)
        self.assertEqual(round(v["left"]), 90)
        self.assertIsNone(v["done"])
        v = c._timer_tick(c.timer["end"] + 0.1, idle=500)
        self.assertIsNotNone(v["done"])
        self.assertIsNone(c._timer_tick(c.timer["done_at"] + 3, idle=0.2))     # a key pressed: it stops

    def test_pomodoro_goes_from_work_to_break_to_work(self):
        c = self.clock
        c.start_pomodoro()
        self.assertEqual((c.timer["phase"], c.timer["round"]), ("work", 1))
        end = c.timer["end"]
        c._timer_tick(end + 0.1, idle=500)
        c._timer_tick(end + 5, idle=500)
        self.assertEqual(c.timer["phase"], "short")
        end = c.timer["end"]
        c._timer_tick(end + 0.1, idle=500)
        c._timer_tick(end + 5, idle=500)
        self.assertEqual((c.timer["phase"], c.timer["round"]), ("work", 2))

    def test_alarm_fires_once_on_its_days_and_stops_on_input(self):
        c = self.clock
        c.apply(kc.clean_settings({"alarms": [{"time": "07:30", "days": [4], "color": "#00ff00"}]}))
        friday, saturday = WALL.replace(hour=7, minute=30), WALL.replace(day=21, hour=7, minute=30)
        c._alarm_check(100.0, saturday)
        self.assertIsNone(c.alarm)
        c._alarm_check(100.0, friday)
        self.assertEqual(c.alarm["color"], "#00ff00")
        c.alarm = None
        c._alarm_check(130.0, friday)                                   # same minute: not again
        self.assertIsNone(c.alarm)
        c._alarm_check(100.0, friday.replace(day=27))
        self.assertIsNotNone(c._alarm_tick(105.0, idle=50))
        self.assertIsNone(c._alarm_tick(110.0, idle=0.1))

    def test_timer_and_alarm_frames(self):
        m = kc.Model("tkl-iso")
        r = kc.Renderer(m, kc.clean_settings({}))
        timer = {"left": 125.0, "total": 600.0, "color": "#ff2e63", "done": None}
        f = r.frame(1.0, WALL, extra={"timer": timer})
        lit = {k for k, c in f.items() if sum(c)}
        self.assertTrue(set(kc.classic_keys(m, "0", 0)) <= lit and set(kc.classic_keys(m, "3", 1)) <= lit)
        self.assertIn("PrtSc", lit)                                     # the block of the time left...
        self.assertNotIn("PgDn", lit)                                   # ...emptying from its end
        self.assertNotIn("LCtrl", lit)                                  # nothing on the bottom row
        over = r.frame(1.0, WALL, extra={"timer": dict(timer, left=0.0, done=0.0)})
        self.assertTrue(all(sum(c) > 0 for c in over.values()))
        alarm = {"for": 2.0, "color": "#ff1a1a"}
        self.assertTrue(all(sum(c) > 0 for c in r.frame(1.0, WALL, extra={"alarm": alarm}).values()))

    def test_music_background(self):
        class Music:
            silent, loud, pulse = False, 0.8, 0.5
            level = [1.0] * 4 + [0.0] * 10
        m = kc.Model("tkl-iso")
        for style in kc.MUSIC_STYLES:
            s = kc.clean_settings({"look": {"background": {"mode": "music", "music_style": style, "level": 80}}})
            f = kc.Renderer(m, s).frame(1.0, WALL, music=Music())
            self.assertGreater(sum(f["LCtrl"]), 0, style)
        s = kc.clean_settings({"look": {"background": {"mode": "music", "music_style": "spectrum", "level": 80}}})
        f = kc.Renderer(m, s).frame(1.0, WALL, music=Music())
        self.assertEqual(f["F12"], (0, 0, 0))                            # treble bands are silent here


class Settings(unittest.TestCase):
    def test_defaults_are_clean(self):
        self.assertEqual(kc.clean_settings({}), kc.clean_settings(kc.clean_settings({})))

    def test_junk_is_replaced_by_defaults(self):
        s = kc.clean_settings({"show": {"delay": "soon", "when": "never"}, "display": {"mode": 3, "secs": -4},
                               "look": {"colors": {"hours": "red"}, "brightness": 900, "gradient": ["#fff"]},
                               "night": {"from": "25:00"}, "keyboard": {"model": "typewriter"}})
        d = kc.clean_settings({})
        self.assertEqual(s["show"]["delay"], d["show"]["delay"])
        self.assertEqual(s["show"]["when"], "idle")
        self.assertEqual(s["display"]["mode"], "time")
        self.assertEqual(s["display"]["secs"], 0.5)
        self.assertEqual(s["look"]["colors"]["hours"], d["look"]["colors"]["hours"])
        self.assertEqual(s["look"]["brightness"], 100)
        self.assertEqual(s["look"]["gradient"], d["look"]["gradient"])
        self.assertEqual(s["night"]["from"], "22:00")
        self.assertEqual(s["keyboard"]["model"], "auto")

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "settings.json")
            s = kc.apply_theme(kc.clean_settings({}), "matrix")
            kc.save_settings(s, path)
            self.assertEqual(kc.load_settings(path), s)
            with open(path, "w") as f:
                f.write("{broken")
            self.assertEqual(kc.load_settings(path), kc.clean_settings({}))

    def test_custom_sequence(self):
        s = kc.clean_settings({"display": {"mode": "custom", "sequence": [
            {"show": "day", "secs": 3}, {"scroll": "HELLO"}, {"show": "nope"}, "junk", {"show": "month"}]}})
        self.assertEqual(s["display"]["sequence"], [{"show": "day", "secs": 3}, {"show": "month", "secs": 2.5}])
        r = kc.Renderer(kc.Model("tkl-iso"), s)
        self.assertEqual(len(r.items), 2)
        self.assertEqual(kc.clean_settings({"display": {"mode": "scroll"}})["display"]["mode"], "time")

    def test_night_hours(self):
        n = {"on": True, "from": "22:00", "to": "07:00"}
        self.assertTrue(kc.night_now(n, WALL.replace(hour=23)))
        self.assertTrue(kc.night_now(n, WALL.replace(hour=3)))
        self.assertFalse(kc.night_now(n, WALL.replace(hour=13)))
        self.assertFalse(kc.night_now({**n, "on": False}, WALL.replace(hour=23)))

    def test_hotkeys(self):
        self.assertEqual(kc.parse_hotkey("Ctrl+Alt+H"), (0x3, ord("H")))
        self.assertEqual(kc.parse_hotkey("win+shift+F9"), (0xC, 0x78))
        self.assertIsNone(kc.parse_hotkey("H"))
        self.assertIsNone(kc.parse_hotkey("Ctrl+Banana"))


if __name__ == "__main__":
    unittest.main()
