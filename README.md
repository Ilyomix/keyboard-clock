# Keyboard Clock

The time in big digits on your RGB keyboard while you are away.

Keyboard Clock is a free, open-source Windows app for Logitech G keyboards with per-key RGB lighting. When you step
away, it draws the hours and minutes key by key, then gives the lighting back to G HUB as soon as you touch a key.

- Hours and minutes (and the date if you like), with fades, slides, wipes or dissolves
- Themes, gradients, colors of the day, a background that breathes, twinkles or follows your music
- A timer, Pomodoro cycles and alarms that flash the keyboard
- A font editor: draw each digit key by key, on the left and on the right
- Night hours, lock screen, full-screen games, a global shortcut
- An icon next to the clock, a window in six languages, starts with Windows

Requirements: Windows 10 or 11, Logitech G HUB with *Allow games & applications to control my lighting* on.

```bash
python keyboard_clock.py            # the app (icon next to the clock and its window)
python keyboard_clock.py --demo     # every look on the keyboard, then exit
python keyboard_clock.py --help     # all the options
```

MIT License. Logitech, Logitech G and G HUB are trademarks of Logitech. Keyboard Clock is an independent project,
not affiliated with or endorsed by Logitech. The window uses the Inter font (SIL Open Font License,
[licenses/Inter-OFL.txt](licenses/Inter-OFL.txt)).
