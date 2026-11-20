# Privacy policy

Keyboard Clock runs on your computer. It has no account, no telemetry, no analytics and no ads, and it collects no personal data.

## Network

| When | Where | What is sent | Turn it off |
|---|---|---|---|
| About 30 seconds after Keyboard Clock starts, then once a day. On by default, except in the Microsoft Store version, which the Store updates | `api.github.com`, to read the latest release | An HTTPS request with the user agent `KeyboardClock/<version>` | Untick *Check for a new version once a day* in the installer, switch off *Check automatically* in the app, or run `keyboard-clock --check-updates off` |
| When you click *Check for updates* or *Update to …* | `api.github.com` and `github.com`, to read the latest release and download it with its `SHA256SUMS.txt` | HTTPS requests with the same user agent | Only happens when you click |

GitHub sees your IP address with its requests, as with any website: see the [GitHub General Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). Keyboard Clock sends GitHub nothing else.

## Your keyboard

Keyboard Clock talks to your keyboard's lighting on your PC only: through the LED SDK of Logitech G HUB, straight to the keyboard over HID LampArray (Windows Dynamic Lighting), or through the OpenRGB SDK server on your own computer (`127.0.0.1`). It sends key colors only.

## Keyboard and mouse activity

Keyboard Clock asks Windows how long ago the keyboard or the mouse was last used, to know when you are away. It never reads which keys you press or what you type. If you set a shortcut, Windows tells Keyboard Clock only when that shortcut is pressed.

## Apps

Once a second, Keyboard Clock asks Windows whether an app is full screen (to stay hidden during games and videos) and, only if you listed apps to hide it for, which apps are running. Nothing is kept or sent.

## Sound

Only while the *Music* background shows, Keyboard Clock listens to what Windows plays on its default output (the sound you hear, never a microphone) to light the keys with the music. The sound is analysed in memory and dropped right away: it is never recorded, saved or sent. Ten seconds after the Music background stops, Keyboard Clock stops listening.

## Files on your computer

`%LOCALAPPDATA%\KeyboardClock` holds your settings (`settings.json`, with your colors, alarms and digits), the app's icons, and the log of the last two sessions. Uninstalling Keyboard Clock removes this folder, the startup entry, the Start menu shortcut and the name Windows shows on its notifications. For the portable and Python versions, `keyboard-clock --uninstall` does the same.

## Changes

This policy is part of the Keyboard Clock repository: its history shows every change.
