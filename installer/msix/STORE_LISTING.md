# Keyboard Clock on the Microsoft Store

What to enter in [Partner Center](https://partner.microsoft.com/dashboard/apps-and-games/overview) for Keyboard Clock's Store listing, in its six languages. The package is built by the release workflow (`installer/msix/make_msix.py`, build artifact `KeyboardClock-<version>`); the screenshots by `python installer/msix/store_screenshots.py` (in `build/store/<language>/`).

Every field below stays within Partner Center's limits: description 10,000 characters, short description 1,000, what's new 1,500, up to 20 features of 200 characters, up to 7 search terms of 30 characters (21 words in all), captions and system requirements 200.

## Submission options

| Field | Value |
|---|---|
| Pricing | Free, all markets |
| Category | Utilities & tools |
| Privacy policy URL | https://github.com/Ilyomix/keyboard-clock/blob/main/PRIVACY.md |
| Website | https://ilyomix.github.io/keyboard-clock/ (or the page in each language: `https://ilyomix.github.io/keyboard-clock/fr/`, `es/`, `de/`, `it/`, `pt/`) |
| Support contact info | https://github.com/Ilyomix/keyboard-clock/issues |
| Age ratings | IARC questionnaire: a utility; no violence, sex, gambling or purchases; users don't chat or share content with each other; no location sharing; no web browser. Expected rating: 3+ / Everyone |
| Display mode | Not a game: no Xbox or gaming options |

### Restricted capabilities: why runFullTrust

```text
Keyboard Clock is a Win32 desktop app (Python, packaged with PyInstaller). It needs runFullTrust to drive keyboards through Logitech G HUB's LED SDK, HID LampArray (Windows Dynamic Lighting) or the OpenRGB SDK on 127.0.0.1, notice when the PC is idle or locked, register a global shortcut, show an icon in the notification area and start at sign-in.
```

### Notes for certification

```text
Keyboard Clock is a Win32 desktop app (Python, packaged with PyInstaller) that shows the time in big digits on a per-key RGB keyboard while the user is away from the PC.

Why runFullTrust: it drives keyboards through Logitech G HUB's LED SDK (loaded from G HUB's install folder), HID LampArray (Windows Dynamic Lighting) or the OpenRGB SDK server on 127.0.0.1:6742; it notices when the PC is idle or locked and when a game or video is full screen; it registers a global shortcut (Ctrl+Alt+H), shows an icon in the notification area and starts at sign-in through its StartupTask (the user can turn it off in Settings > Apps > Startup). While the "Music" background is on, it reads the default audio output through WASAPI loopback (never a microphone) and records nothing.

Testing without an RGB keyboard: the app starts and its window opens; its pages show a live preview of the clock on a drawn keyboard.

No account or sign-in, no in-app purchases, no ads, no telemetry. In the Store version the app's own update checker is off: the Store updates it.
```

## English (en-us)

Product name: **Keyboard Clock**. Website for this language: https://ilyomix.github.io/keyboard-clock/

### Description

```text
Step away from your PC and Keyboard Clock turns your keyboard into a clock you can read from across the room. First the hours, then the minutes, in two big digits drawn key by key over the F-keys, the number row and the letters, one digit on each half of the keyboard. The seconds fill the nine keys above the arrows. Touch the mouse or any key and your usual lighting is back at once.

It also runs a timer, Pomodoro cycles and alarms right on the keys, lights up with your music, and lets you draw your own digits.

• Shows up when you leave: after a delay you pick (10 seconds to 30 minutes), as soon as you lock the PC, all the time, or with a shortcut (Ctrl+Alt+H).
• Stays out of the way: hidden while a game or a video is full screen, or while apps you choose are running.
• Themes and colors: Neon, Sunset, Ocean, Matrix, Rainbow, White, Night red, colors that follow the time of day, or your own.
• Backgrounds: a dim color, a gradient, breathing, twinkling stars, or the music your PC plays.
• Timer, Pomodoro, alarms and reminders, a night mode and an hourly chime.
• A font editor to redraw any digit, key by key.

Which keyboards work
Keyboards with per-key RGB and a row of F-keys (TKL or full size), in any layout: AZERTY, QWERTY, QWERTZ, ISO or ANSI.
• Logitech G (G PRO, G915, G815, G513…) through G HUB: in G HUB's settings, turn on "Allow games & applications to control my lighting".
• Razer, Corsair, ASUS ROG, SteelSeries, HyperX and others through Windows Dynamic Lighting (Windows 11): switch Dynamic Lighting off for that keyboard in Settings.
• Keyboards supported by OpenRGB, with its SDK server on.
Not supported: 60% and 65% keyboards, and keyboards lit by zones only.

Keyboard Clock is free and open source (MIT license): no account, no ads, no telemetry. Source code and the list of tested keyboards: https://github.com/Ilyomix/keyboard-clock
```

### What's new in this version

```text
First version on the Microsoft Store. The Store keeps Keyboard Clock up to date, and Windows starts it when you sign in (you can turn that off in Settings > Apps > Startup). Used Keyboard Clock before? Your settings carry over.
```

### Product features

```text
The time in two big digits drawn key by key, readable from across the room
Shows up after a delay you pick, when you lock the PC, all the time, or with Ctrl+Alt+H
Hidden while a game or a video is full screen, or while apps you choose are running
Your usual lighting comes back the moment you touch the mouse or a key
Themes, colors that follow the time of day, gradients and per-digit colors
Backgrounds: a dim color, a gradient, breathing, stars, or the music your PC plays
Fade, slide, wipe and dissolve transitions, and the date in between
Timer and Pomodoro on the keys, started from the icon next to the clock
Alarms and reminders: the keyboard flashes until you press a key
Font editor: redraw any digit, left and right, with a live preview
Night mode (dim, red or off) and a wave of light on the hour
Logitech G (G HUB), Windows Dynamic Lighting and OpenRGB keyboards, any layout
A window with a live preview of your keyboard
6 languages: English, French, Spanish, German, Italian and Portuguese
Free and open source: no account, no ads, no telemetry
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/en/1-clock.png` | Clock: when and how the time shows, with a live preview of your keyboard |
| `build/store/en/2-look.png` | Look: themes, colors and backgrounds |
| `build/store/en/3-timer.png` | Timer & alarms: a timer, Pomodoro cycles and alarms |
| `build/store/en/4-font.png` | Font: the digit 8 redrawn on the right half of the keyboard |

### Short description

```text
The time, in big digits, on your RGB keyboard. Step away from your PC and your keyboard becomes a clock you can read from across the room.
```

### Search terms (one per box)

```text
keyboard clock
RGB keyboard
Logitech G HUB
Dynamic Lighting
OpenRGB
Pomodoro timer
per-key RGB
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Free and open source, MIT license.
```

### Additional system requirements (minimum hardware)

```text
A per-key RGB keyboard with a row of F-keys (TKL or full size)
Logitech G HUB, Windows 11 Dynamic Lighting or OpenRGB to drive it
```

## Français (fr-fr)

Product name: **Keyboard Clock**. Website for this language: https://ilyomix.github.io/keyboard-clock/fr/

### Description

```text
Éloignez-vous de votre PC : Keyboard Clock transforme votre clavier en horloge lisible depuis l'autre bout de la pièce. D'abord les heures, puis les minutes, en deux gros chiffres dessinés touche par touche sur les touches F, la rangée des chiffres et les lettres, un chiffre sur chaque moitié du clavier. Les secondes remplissent les neuf touches au-dessus des flèches. Touchez la souris ou une touche, et votre éclairage habituel revient aussitôt.

Il gère aussi un minuteur, des cycles Pomodoro et des alarmes directement sur les touches, s'anime au rythme de votre musique et vous permet de dessiner vos propres chiffres.

• S'affiche quand vous partez : après le délai de votre choix (de 10 secondes à 30 minutes), dès que vous verrouillez le PC, en permanence, ou avec un raccourci (Ctrl+Alt+H).
• Discret : masqué quand un jeu ou une vidéo est en plein écran, ou quand des applications de votre choix sont ouvertes.
• Thèmes et couleurs : Néon, Coucher de soleil, Océan, Matrix, Arc-en-ciel, Blanc, Rouge nuit, des couleurs qui suivent le moment de la journée, ou les vôtres.
• Fonds : une couleur tamisée, un dégradé, une respiration, des étoiles scintillantes, ou la musique de votre PC.
• Minuteur, Pomodoro, alarmes et rappels, mode nuit et carillon horaire.
• Un éditeur de police pour redessiner chaque chiffre, touche par touche.

Quels claviers
Les claviers avec un éclairage RGB par touche et une rangée de touches F (TKL ou format complet), quelle que soit la disposition : AZERTY, QWERTY, QWERTZ, ISO ou ANSI.
• Logitech G (G PRO, G915, G815, G513…) via G HUB : dans les paramètres de G HUB, activez « Autoriser les jeux et les applications à contrôler mon éclairage ».
• Razer, Corsair, ASUS ROG, SteelSeries, HyperX et d'autres via l'Éclairage dynamique de Windows (Windows 11) : désactivez l'Éclairage dynamique pour ce clavier dans les Paramètres.
• Les claviers pris en charge par OpenRGB, avec son serveur SDK démarré.
Non pris en charge : les claviers 60 % et 65 %, et les claviers éclairés par zones seulement.

Keyboard Clock est gratuit et open source (licence MIT) : pas de compte, pas de pub, pas de télémétrie. Code source et liste des claviers testés : https://github.com/Ilyomix/keyboard-clock
```

### What's new in this version

```text
Première version sur le Microsoft Store. Le Store tient Keyboard Clock à jour, et Windows le lance à l'ouverture de session (désactivable dans Paramètres > Applications > Démarrage). Vous utilisiez déjà Keyboard Clock ? Vos réglages sont conservés.
```

### Product features

```text
L'heure en deux gros chiffres dessinés touche par touche, lisible depuis l'autre bout de la pièce
S'affiche après le délai de votre choix, au verrouillage du PC, en permanence ou avec Ctrl+Alt+H
Masqué quand un jeu ou une vidéo est en plein écran, ou quand des applications de votre choix sont ouvertes
Votre éclairage habituel revient dès que vous touchez la souris ou une touche
Thèmes, couleurs qui suivent le moment de la journée, dégradés et une couleur par chiffre
Fonds : une couleur tamisée, un dégradé, une respiration, des étoiles, ou la musique de votre PC
Transitions en fondu, glissement, balayage ou dissolution, et la date en alternance
Minuteur et Pomodoro sur les touches, lancés depuis l'icône près de l'horloge
Alarmes et rappels : le clavier clignote jusqu'à ce que vous appuyiez sur une touche
Éditeur de police : redessinez chaque chiffre, à gauche et à droite, avec un aperçu en direct
Mode nuit (tamisé, rouge ou éteint) et une vague de lumière à chaque heure pile
Claviers Logitech G (G HUB), Éclairage dynamique de Windows et OpenRGB, toutes dispositions
Une fenêtre avec un aperçu en direct de votre clavier
6 langues : français, anglais, espagnol, allemand, italien et portugais
Gratuit et open source : pas de compte, pas de pub, pas de télémétrie
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/fr/1-clock.png` | Horloge : quand et comment l'heure s'affiche, avec un aperçu en direct de votre clavier |
| `build/store/fr/2-look.png` | Apparence : thèmes, couleurs et fonds |
| `build/store/fr/3-timer.png` | Minuteur et alarmes : minuteur, cycles Pomodoro et alarmes |
| `build/store/fr/4-font.png` | Police : le chiffre 8 redessiné sur la moitié droite du clavier |

### Short description

```text
L'heure en gros chiffres sur votre clavier RGB. Éloignez-vous de votre PC : votre clavier devient une horloge lisible depuis l'autre bout de la pièce.
```

### Search terms (one per box)

```text
horloge clavier
clavier RGB
Logitech G HUB
Éclairage dynamique
OpenRGB
minuteur Pomodoro
RGB par touche
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Gratuit et open source, licence MIT.
```

### Additional system requirements (minimum hardware)

```text
Un clavier RGB par touche avec une rangée de touches F (TKL ou format complet)
Logitech G HUB, l'Éclairage dynamique de Windows 11 ou OpenRGB pour le piloter
```

## Español (es-es)

Product name: **Keyboard Clock**. Website for this language: https://ilyomix.github.io/keyboard-clock/es/

### Description

```text
Deja tu PC y Keyboard Clock convierte tu teclado en un reloj que puedes leer desde la otra punta de la habitación. Primero las horas y luego los minutos, en dos grandes dígitos dibujados tecla a tecla sobre las teclas de función, la fila de números y las letras, un dígito en cada mitad del teclado. Los segundos llenan las nueve teclas sobre las flechas. Toca el ratón o cualquier tecla y tu iluminación de siempre vuelve al instante.

También ejecuta un temporizador, ciclos Pomodoro y alarmas directamente en las teclas, se ilumina con tu música y te permite dibujar tus propios dígitos.

• Aparece cuando te vas: tras el tiempo que elijas (de 10 segundos a 30 minutos), en cuanto bloqueas el PC, siempre o con un atajo (Ctrl+Alt+H).
• No estorba: se oculta mientras un juego o un vídeo está en pantalla completa, o mientras se ejecutan las apps que elijas.
• Temas y colores: Neón, Atardecer, Océano, Matrix, Arcoíris, Blanco, Rojo noche, colores que siguen la hora del día, o los tuyos.
• Fondos: un color tenue, un degradado, respiración, estrellas titilantes o la música que suena en tu PC.
• Temporizador, Pomodoro, alarmas y recordatorios, modo noche y campanada horaria.
• Un editor de fuente para redibujar cualquier dígito, tecla a tecla.

Qué teclados funcionan
Teclados con RGB por tecla y una fila de teclas de función (TKL o tamaño completo), con cualquier distribución: AZERTY, QWERTY, QWERTZ, ISO o ANSI.
• Logitech G (G PRO, G915, G815, G513…) a través de G HUB: en la configuración de G HUB, activa «Allow games & applications to control my lighting».
• Razer, Corsair, ASUS ROG, SteelSeries, HyperX y otros a través de la Iluminación dinámica de Windows (Windows 11): desactiva la Iluminación dinámica para ese teclado en Configuración.
• Teclados compatibles con OpenRGB, con su servidor SDK activo.
No compatibles: teclados 60 % y 65 %, y teclados iluminados solo por zonas.

Keyboard Clock es gratuito y de código abierto (licencia MIT): sin cuenta, sin anuncios, sin telemetría. Código fuente y lista de teclados probados: https://github.com/Ilyomix/keyboard-clock
```

### What's new in this version

```text
Primera versión en Microsoft Store. La Store mantiene Keyboard Clock actualizado y Windows lo inicia al iniciar sesión (puedes desactivarlo en Configuración > Aplicaciones > Inicio). ¿Ya usabas Keyboard Clock? Se conservan tus ajustes.
```

### Product features

```text
La hora en dos grandes dígitos dibujados tecla a tecla, legible desde la otra punta de la habitación
Aparece tras el tiempo que elijas, al bloquear el PC, siempre o con Ctrl+Alt+H
Se oculta mientras un juego o un vídeo está en pantalla completa, o mientras se ejecutan las apps que elijas
Tu iluminación de siempre vuelve en cuanto tocas el ratón o una tecla
Temas, colores que siguen la hora del día, degradados y colores por dígito
Fondos: un color tenue, un degradado, respiración, estrellas o la música de tu PC
Transiciones de fundido, deslizamiento, barrido o disolución, y la fecha intercalada
Temporizador y Pomodoro en las teclas, desde el icono junto al reloj
Alarmas y recordatorios: el teclado parpadea hasta que pulses una tecla
Editor de fuente: redibuja cualquier dígito, a la izquierda y a la derecha, con vista previa en vivo
Modo noche (atenuado, rojo o apagado) y una ola de luz a cada hora en punto
Teclados Logitech G (G HUB), Iluminación dinámica de Windows y OpenRGB, con cualquier distribución
Una ventana con vista previa en vivo de tu teclado
6 idiomas: español, inglés, francés, alemán, italiano y portugués
Gratuito y de código abierto: sin cuenta, sin anuncios, sin telemetría
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/es/1-clock.png` | Reloj: cuándo y cómo aparece la hora, con vista previa en vivo de tu teclado |
| `build/store/es/2-look.png` | Aspecto: temas, colores y fondos |
| `build/store/es/3-timer.png` | Temporizador y alarmas: temporizador, ciclos Pomodoro y alarmas |
| `build/store/es/4-font.png` | Fuente: el dígito 8 redibujado en la mitad derecha del teclado |

### Short description

```text
La hora en grande en tu teclado RGB. Deja tu PC y tu teclado se convierte en un reloj que puedes leer desde la otra punta de la habitación.
```

### Search terms (one per box)

```text
reloj teclado
teclado RGB
Logitech G HUB
Iluminación dinámica
OpenRGB
temporizador Pomodoro
RGB por tecla
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Gratuito y de código abierto, licencia MIT.
```

### Additional system requirements (minimum hardware)

```text
Un teclado RGB por tecla con una fila de teclas de función (TKL o tamaño completo)
Logitech G HUB, la Iluminación dinámica de Windows 11 u OpenRGB para controlarlo
```

## Deutsch (de-de)

Product name: **Keyboard Clock**. Website for this language: https://ilyomix.github.io/keyboard-clock/de/

### Description

```text
Geh vom PC weg, und Keyboard Clock macht deine Tastatur zu einer Uhr, die du noch vom anderen Ende des Raums ablesen kannst. Erst die Stunden, dann die Minuten, in zwei großen Ziffern, die Taste für Taste über F-Tasten, Zahlenreihe und Buchstaben gezeichnet sind, eine Ziffer auf jeder Tastaturhälfte. Die Sekunden füllen die neun Tasten über den Pfeiltasten. Berühre die Maus oder eine beliebige Taste, und deine gewohnte Beleuchtung ist sofort zurück.

Dazu kommen ein Timer, Pomodoro-Runden und Wecker direkt auf den Tasten, Licht im Takt deiner Musik und die Möglichkeit, eigene Ziffern zu zeichnen.

• Erscheint, wenn du gehst: nach einer Wartezeit deiner Wahl (10 Sekunden bis 30 Minuten), sobald du den PC sperrst, dauerhaft oder per Tastenkürzel (Strg+Alt+H).
• Stört nicht: ausgeblendet, solange ein Spiel oder Video im Vollbild läuft oder Apps deiner Wahl geöffnet sind.
• Designs und Farben: Neon, Sonnenuntergang, Ozean, Matrix, Regenbogen, Weiß, Nachtrot, Farben, die der Tageszeit folgen, oder deine eigenen.
• Hintergründe: eine gedimmte Farbe, ein Verlauf, Atmen, funkelnde Sterne oder die Musik, die dein PC abspielt.
• Timer, Pomodoro, Wecker und Erinnerungen, Nachtmodus und Stundenschlag.
• Ein Schrifteditor, um jede Ziffer Taste für Taste neu zu zeichnen.

Welche Tastaturen funktionieren
Tastaturen mit RGB pro Taste und einer F-Tasten-Reihe (TKL oder Full Size), in jedem Layout: AZERTY, QWERTY, QWERTZ, ISO oder ANSI.
• Logitech G (G PRO, G915, G815, G513…) über G HUB: In den G-HUB-Einstellungen „Allow games & applications to control my lighting“ einschalten.
• Razer, Corsair, ASUS ROG, SteelSeries, HyperX und andere über die dynamische Beleuchtung von Windows (Windows 11): die dynamische Beleuchtung für diese Tastatur in den Einstellungen ausschalten.
• Tastaturen, die OpenRGB unterstützt, mit laufendem SDK-Server.
Nicht unterstützt: 60-%- und 65-%-Tastaturen sowie Tastaturen, die nur in Zonen beleuchtet sind.

Keyboard Clock ist kostenlos und Open Source (MIT-Lizenz): kein Konto, keine Werbung, keine Telemetrie. Quellcode und Liste der getesteten Tastaturen: https://github.com/Ilyomix/keyboard-clock
```

### What's new in this version

```text
Erste Version im Microsoft Store. Der Store hält Keyboard Clock aktuell, und Windows startet es bei der Anmeldung (abschaltbar unter Einstellungen > Apps > Autostart). Du hast Keyboard Clock schon benutzt? Deine Einstellungen bleiben erhalten.
```

### Product features

```text
Die Uhrzeit in zwei großen Ziffern, Taste für Taste gezeichnet, vom anderen Ende des Raums lesbar
Erscheint nach einer Wartezeit deiner Wahl, beim Sperren des PCs, dauerhaft oder mit Strg+Alt+H
Ausgeblendet, solange ein Spiel oder Video im Vollbild läuft oder Apps deiner Wahl geöffnet sind
Deine gewohnte Beleuchtung kommt zurück, sobald du die Maus oder eine Taste berührst
Designs, Farben, die der Tageszeit folgen, Verläufe und Farben pro Ziffer
Hintergründe: eine gedimmte Farbe, ein Verlauf, Atmen, Sterne oder die Musik deines PCs
Übergänge: Überblenden, Schieben, Wischen oder Auflösen, und das Datum dazwischen
Timer und Pomodoro auf den Tasten, gestartet über das Symbol neben der Uhr
Wecker und Erinnerungen: Die Tastatur blinkt, bis du eine Taste drückst
Schrifteditor: Zeichne jede Ziffer neu, links und rechts, mit Live-Vorschau
Nachtmodus (gedimmt, rot oder aus) und zur vollen Stunde eine Lichtwelle
Tastaturen von Logitech G (G HUB), mit dynamischer Beleuchtung von Windows oder OpenRGB, jedes Layout
Ein Fenster mit Live-Vorschau deiner Tastatur
6 Sprachen: Deutsch, Englisch, Französisch, Spanisch, Italienisch und Portugiesisch
Kostenlos und Open Source: kein Konto, keine Werbung, keine Telemetrie
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/de/1-clock.png` | Uhr: wann und wie die Uhrzeit erscheint, mit Live-Vorschau deiner Tastatur |
| `build/store/de/2-look.png` | Aussehen: Designs, Farben und Hintergründe |
| `build/store/de/3-timer.png` | Timer & Wecker: Timer, Pomodoro-Runden und Wecker |
| `build/store/de/4-font.png` | Schrift: die Ziffer 8, neu gezeichnet auf der rechten Tastaturhälfte |

### Short description

```text
Die Uhrzeit in großen Ziffern auf deiner RGB-Tastatur. Geh vom PC weg, und deine Tastatur wird zu einer Uhr, die du noch vom anderen Ende des Raums ablesen kannst.
```

### Search terms (one per box)

```text
Tastatur Uhr
RGB Tastatur
Logitech G HUB
Dynamische Beleuchtung
OpenRGB
Pomodoro Timer
RGB pro Taste
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Kostenlos und Open Source, MIT-Lizenz.
```

### Additional system requirements (minimum hardware)

```text
Eine Tastatur mit RGB pro Taste und einer F-Tasten-Reihe (TKL oder Full Size)
Logitech G HUB, die dynamische Beleuchtung von Windows 11 oder OpenRGB zur Steuerung
```

## Italiano (it-it)

Product name: **Keyboard Clock**. Website for this language: https://ilyomix.github.io/keyboard-clock/it/

### Description

```text
Allontanati dal PC e Keyboard Clock trasforma la tua tastiera in un orologio che leggi dall'altra parte della stanza. Prima le ore, poi i minuti, in due grandi cifre disegnate tasto per tasto sui tasti funzione, sulla fila dei numeri e sulle lettere, una cifra su ogni metà della tastiera. I secondi riempiono i nove tasti sopra le frecce. Tocca il mouse o un tasto qualsiasi e la tua illuminazione di sempre torna subito.

Gestisce anche un timer, cicli Pomodoro e sveglie direttamente sui tasti, si accende con la tua musica e ti permette di disegnare le tue cifre.

• Appare quando ti allontani: dopo un ritardo a tua scelta (da 10 secondi a 30 minuti), appena blocchi il PC, sempre, oppure con una scorciatoia (Ctrl+Alt+H).
• Non dà fastidio: resta nascosto quando un gioco o un video è a schermo intero, o mentre sono aperte le app che scegli tu.
• Temi e colori: Neon, Tramonto, Oceano, Matrix, Arcobaleno, Bianco, Rosso notte, colori che seguono l'ora del giorno, oppure i tuoi.
• Sfondi: un colore soffuso, una sfumatura, effetto respiro, stelle che brillano, oppure la musica che il PC sta riproducendo.
• Timer, Pomodoro, sveglie e promemoria, modalità notte e rintocco orario.
• Un editor del carattere per ridisegnare ogni cifra, tasto per tasto.

Quali tastiere funzionano
Tastiere con RGB per tasto e una fila di tasti funzione (TKL o full size), con qualsiasi layout: AZERTY, QWERTY, QWERTZ, ISO o ANSI.
• Logitech G (G PRO, G915, G815, G513…) tramite G HUB: nelle impostazioni di G HUB attiva «Allow games & applications to control my lighting».
• Razer, Corsair, ASUS ROG, SteelSeries, HyperX e altre tramite l'Illuminazione dinamica di Windows (Windows 11): disattiva l'Illuminazione dinamica per quella tastiera nelle Impostazioni.
• Tastiere supportate da OpenRGB, con il suo server SDK avviato.
Non supportate: tastiere 60% e 65% e tastiere illuminate solo a zone.

Keyboard Clock è gratuito e open source (licenza MIT): nessun account, nessuna pubblicità, nessuna telemetria. Codice sorgente ed elenco delle tastiere testate: https://github.com/Ilyomix/keyboard-clock
```

### What's new in this version

```text
Prima versione su Microsoft Store. Lo Store tiene aggiornato Keyboard Clock e Windows lo avvia all'accesso (puoi disattivarlo in Impostazioni > App > Avvio). Usavi già Keyboard Clock? Le tue impostazioni restano.
```

### Product features

```text
L'ora in due grandi cifre disegnate tasto per tasto, leggibili dall'altra parte della stanza
Appare dopo un ritardo a tua scelta, quando blocchi il PC, sempre o con Ctrl+Alt+H
Nascosto quando un gioco o un video è a schermo intero, o mentre sono aperte le app che scegli
La tua illuminazione di sempre torna appena tocchi il mouse o un tasto
Temi, colori che seguono l'ora del giorno, sfumature e un colore per ogni cifra
Sfondi: un colore soffuso, una sfumatura, respiro, stelle o la musica del PC
Transizioni a dissolvenza, scorrimento, tendina o dissolvi, e la data in mezzo
Timer e Pomodoro sui tasti, avviati dall'icona accanto all'orologio
Sveglie e promemoria: la tastiera lampeggia finché non premi un tasto
Editor del carattere: ridisegna ogni cifra, a sinistra e a destra, con anteprima dal vivo
Modalità notte (attenuata, rossa o spenta) e un'onda di luce allo scoccare dell'ora
Tastiere Logitech G (G HUB), Illuminazione dinamica di Windows e OpenRGB, con qualsiasi layout
Una finestra con l'anteprima dal vivo della tastiera
6 lingue: italiano, inglese, francese, spagnolo, tedesco e portoghese
Gratuito e open source: nessun account, nessuna pubblicità, nessuna telemetria
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/it/1-clock.png` | Orologio: quando e come appare l'ora, con l'anteprima dal vivo della tastiera |
| `build/store/it/2-look.png` | Aspetto: temi, colori e sfondi |
| `build/store/it/3-timer.png` | Timer e sveglie: timer, cicli Pomodoro e sveglie |
| `build/store/it/4-font.png` | Carattere: la cifra 8 ridisegnata sulla metà destra della tastiera |

### Short description

```text
L'ora a grandi cifre sulla tua tastiera RGB. Allontanati dal PC e la tastiera diventa un orologio che leggi dall'altra parte della stanza.
```

### Search terms (one per box)

```text
orologio tastiera
tastiera RGB
Logitech G HUB
Illuminazione dinamica
OpenRGB
timer Pomodoro
RGB per tasto
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Gratuito e open source, licenza MIT.
```

### Additional system requirements (minimum hardware)

```text
Una tastiera con RGB per tasto e una fila di tasti funzione (TKL o full size)
Logitech G HUB, l'Illuminazione dinamica di Windows 11 o OpenRGB per comandarla
```

## Português (Brasil) (pt-br)

Product name: **Keyboard Clock**. Website for this language: https://ilyomix.github.io/keyboard-clock/pt/

### Description

```text
Quando você sai de perto do PC, o Keyboard Clock transforma o seu teclado em um relógio que dá para ler do outro lado do quarto. Primeiro as horas, depois os minutos, em dois dígitos grandes desenhados tecla por tecla sobre as teclas de função, a fileira de números e as letras, um dígito em cada metade do teclado. Os segundos preenchem as nove teclas acima das setas. Toque no mouse ou em qualquer tecla e a sua iluminação de sempre volta na hora.

Ele também roda um timer, ciclos Pomodoro e alarmes direto nas teclas, acende com a sua música e permite que você desenhe os seus próprios dígitos.

• Aparece quando você sai: depois de um tempo que você escolhe (de 10 segundos a 30 minutos), assim que você bloqueia o PC, o tempo todo ou com um atalho (Ctrl+Alt+H).
• Não atrapalha: fica oculto enquanto um jogo ou um vídeo está em tela cheia, ou enquanto os apps que você escolher estão abertos.
• Temas e cores: Neon, Pôr do sol, Oceano, Matrix, Arco-íris, Branco, Vermelho noturno, cores que acompanham a hora do dia, ou as suas.
• Fundos: uma cor atenuada, um degradê, respiração, estrelas piscando ou a música que toca no seu PC.
• Timer, Pomodoro, alarmes e lembretes, modo noturno e badalada de hora em hora.
• Um editor de fonte para redesenhar qualquer dígito, tecla por tecla.

Quais teclados funcionam
Teclados com RGB por tecla e uma fileira de teclas de função (TKL ou tamanho completo), em qualquer layout: AZERTY, QWERTY, QWERTZ, ISO ou ANSI.
• Logitech G (G PRO, G915, G815, G513…) pelo G HUB: nas configurações do G HUB, ative “Allow games & applications to control my lighting”.
• Razer, Corsair, ASUS ROG, SteelSeries, HyperX e outros pela Iluminação dinâmica do Windows (Windows 11): desative a Iluminação dinâmica para esse teclado nas Configurações.
• Teclados compatíveis com o OpenRGB, com o servidor SDK dele ligado.
Não compatíveis: teclados 60% e 65%, e teclados iluminados só por zonas.

O Keyboard Clock é gratuito e de código aberto (licença MIT): sem conta, sem anúncios, sem telemetria. Código-fonte e lista de teclados testados: https://github.com/Ilyomix/keyboard-clock
```

### What's new in this version

```text
Primeira versão na Microsoft Store. A Store mantém o Keyboard Clock atualizado, e o Windows o inicia quando você entra (dá para desativar em Configurações > Aplicativos > Inicialização). Já usava o Keyboard Clock? Suas configurações são mantidas.
```

### Product features

```text
A hora em dois dígitos grandes desenhados tecla por tecla, legível do outro lado do quarto
Aparece depois de um tempo que você escolhe, ao bloquear o PC, o tempo todo ou com Ctrl+Alt+H
Fica oculto enquanto um jogo ou vídeo está em tela cheia, ou enquanto os apps que você escolher estão abertos
A sua iluminação de sempre volta assim que você toca no mouse ou em uma tecla
Temas, cores que acompanham a hora do dia, degradês e uma cor por dígito
Fundos: uma cor atenuada, um degradê, respiração, estrelas ou a música do seu PC
Transições de esmaecer, deslizar, varredura ou dissolver, e a data entre uma hora e outra
Timer e Pomodoro nas teclas, iniciados pelo ícone ao lado do relógio
Alarmes e lembretes: o teclado pisca até você apertar uma tecla
Editor de fonte: redesenhe qualquer dígito, à esquerda e à direita, com prévia ao vivo
Modo noturno (atenuado, vermelho ou apagado) e uma onda de luz na hora cheia
Teclados Logitech G (G HUB), Iluminação dinâmica do Windows e OpenRGB, em qualquer layout
Uma janela com prévia ao vivo do seu teclado
6 idiomas: português, inglês, francês, espanhol, alemão e italiano
Gratuito e de código aberto: sem conta, sem anúncios, sem telemetria
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/pt/1-clock.png` | Relógio: quando e como a hora aparece, com prévia ao vivo do seu teclado |
| `build/store/pt/2-look.png` | Aparência: temas, cores e fundos |
| `build/store/pt/3-timer.png` | Timer e alarmes: timer, ciclos Pomodoro e alarmes |
| `build/store/pt/4-font.png` | Fonte: o dígito 8 redesenhado na metade direita do teclado |

### Short description

```text
A hora em dígitos grandes no seu teclado RGB. Quando você sai de perto do PC, o teclado vira um relógio que dá para ler do outro lado do quarto.
```

### Search terms (one per box)

```text
relógio teclado
teclado RGB
Logitech G HUB
Iluminação dinâmica
OpenRGB
timer Pomodoro
RGB por tecla
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Gratuito e de código aberto, licença MIT.
```

### Additional system requirements (minimum hardware)

```text
Um teclado RGB por tecla com uma fileira de teclas de função (TKL ou tamanho completo)
Logitech G HUB, a Iluminação dinâmica do Windows 11 ou o OpenRGB para controlá-lo
```
