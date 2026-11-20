"""
Horloge clavier Logitech — affiche l'heure sur les LEDs du clavier quand on ne s'en sert pas.

  - Après 1 minute sans toucher au clavier ni à la souris, l'horloge apparaît en fondu.
    Dès qu'on touche une touche ou la souris, le clavier retrouve l'éclairage de G HUB.
  - Les HEURES (orange) puis les MINUTES (cyan) s'affichent en alternance, avec un fondu.
  - Le carré Impr écran … Page suivante (9 touches) compte les secondes : il se remplit
    en une minute (la touche en cours s'allume progressivement).

Chaque chiffre est un ovale étroit dessiné à la main sur 5 rangées : les touches F, puis
les touches carrées (3 touches en haut et en bas, 4 au milieu grâce au décalage des
rangées). Les deux chiffres tiennent entre F1 et F8, avec au moins une touche d'écart
sur chaque rangée.

     chiffre de gauche   chiffre de droite
      F1 F2 F3 F4   F5 F6 F7 F8             rangée F : 4 cases
       2  3  4        7  8  9               rangée 1 : 3 cases
     A  Z  E  R     Y  U  I  O              rangée 2 : 4 cases (demi-décalée)
      Q  S  D  F     H  J  K  L             rangée 3 : 4 cases
       W  X  C        N  ,  ;               rangée 4 : 3 cases

Utilisation
-----------
  python  horloge_clavier.py            lance l'horloge (Ctrl+C pour arrêter)
  pythonw horloge_clavier.py            lance l'horloge sans fenêtre
  python  horloge_clavier.py --delai 10 l'horloge apparaît après 10 s d'inactivité (défaut 60)
  python  horloge_clavier.py --stop     arrête l'horloge lancée en arrière-plan
  python  horloge_clavier.py --demo     montre quelques heures pour tester
  python  horloge_clavier.py --apercu   enregistre une image du clavier (apercu.png)

Prérequis : G HUB lancé, et dans G HUB > Paramètres, l'option
« Autoriser les jeux et applications à contrôler mon éclairage » activée.
"""

import argparse
import ctypes
import datetime as dt
import os
import struct
import sys
import time
import zlib
from ctypes import wintypes

# ---------------------------------------------------------------------------
# Réglages (couleurs en pourcentage 0-100 : rouge, vert, bleu)
# ---------------------------------------------------------------------------
COULEUR_FOND = (0, 0, 0)
COULEUR_HEURES = (100, 35, 0)
COULEUR_MINUTES = (0, 80, 100)
COULEUR_SECONDES = (60, 60, 60)

DELAI_INACTIVITE = 60   # secondes sans clavier ni souris avant que l'horloge apparaisse
DUREE_AFFICHAGE = 2.5   # secondes pendant lesquelles HH (ou MM) reste affiché
DUREE_FONDU = 0.5       # durée de chaque fondu (disparition, puis apparition)
INTERVALLE_MS = 40      # rafraîchissement (25 images/s, pour des fondus fluides)
INTERVALLE_VEILLE_MS = 200  # vérification de l'activité quand l'horloge est masquée
RAFRAICHISSEMENT_COMPLET = 30  # renvoie toutes les touches toutes les N secondes

# Chiffres dessinés sur les touches (# = touche allumée), une chaîne par rangée
# (voir le schéma en haut du fichier) : touches F (4 cases), puis 3 cases, 4 cases
# décalées d'une demi-touche vers la gauche, 4 cases, 3 cases. Un chiffre de 4 chaînes
# (le 0) n'utilise pas les touches F.
# Les touches F ne tombent pas pareil au-dessus des deux chiffres (F1-F4 sont alignées
# sur 2-3-4-5, F5-F8 sont décalées d'une demi-touche) : la rangée F peut donc être
# un couple (chiffre de gauche, chiffre de droite).
BARRE = ("###.", "####")   # barre du haut : F1-F3 à gauche, F5-F8 à droite
CHIFFRES = {
    "0": ["###", "#..#", "#..#", "###"],              # sans les touches F (plus court)
    "1": ["..#.", ".##", "..#.", "..#.", "..#"],
    "2": [BARRE, "..#", "####", "#...", "###"],
    "3": [BARRE, "..#", ".###", "...#", "###"],
    "4": [("#.#.", "#..#"), "#.#", "####", "...#", "..#"],
    "5": [BARRE, "#..", "####", "...#", "###"],
    "6": [(".#..", ".#.."), "#..", "####", "#..#", "###"],   # petit crochet (F2 / F6)
    "7": [BARRE, "..#", "..#.", ".#..", "#.."],
    "8": [BARRE, "#.#", "####", "#..#", "###"],
    "9": [BARRE, "#.#", ".###", "...#", ".##"],       # queue recourbée
}
# Position physique (en touches) de la 1re case de chaque rangée, par rapport au chiffre
DEBUT_RANGEE = {0: 0.0, 1: -0.5, 2: -0.25, 3: 0.25}
POSITIONS_CHIFFRES = (2.5, 7.5)  # centre de la touche « 2 » (chiffre de gauche) et « 7 » (droite)
TOUCHES_F = ([0x3B, 0x3C, 0x3D, 0x3E],   # F1 F2 F3 F4 (chiffre de gauche)
             [0x3F, 0x40, 0x41, 0x42])   # F5 F6 F7 F8 (chiffre de droite)

# Secondes : le carré Impr écran … Page suivante, rempli dans l'ordre de lecture
TOUCHES_SECONDES = [0x137, 0x46, 0x145,    # Impr écran, Arrêt défil, Pause
                    0x152, 0x147, 0x149,   # Inser, Début, Page préc.
                    0x153, 0x14F, 0x151]   # Suppr, Fin, Page suiv.

# Disposition physique du G PRO (TKL ISO-FR) : (code, x, y, largeur) en unités de touche.
# Codes = enum KeyName du SDK Logitech (position physique, valable en AZERTY).
DISPOSITION = (
    [(0x01, 0, 0, 1)]
    + [(0x3B + i, 2 + i, 0, 1) for i in range(4)]
    + [(0x3F + i, 6.5 + i, 0, 1) for i in range(4)]
    + [(code, 11 + i, 0, 1) for i, code in enumerate([0x43, 0x44, 0x57, 0x58])]
    + [(0x137, 15.25, 0, 1), (0x46, 16.25, 0, 1), (0x145, 17.25, 0, 1)]
    + [(0x29, 0, 1.5, 1)] + [(0x02 + i, 1 + i, 1.5, 1) for i in range(12)] + [(0x0E, 13, 1.5, 2)]
    + [(0x152, 15.25, 1.5, 1), (0x147, 16.25, 1.5, 1), (0x149, 17.25, 1.5, 1)]
    + [(0x0F, 0, 2.5, 1.5)] + [(0x10 + i, 1.5 + i, 2.5, 1) for i in range(12)] + [(0x1C, 13.5, 2.5, 1.5)]
    + [(0x153, 15.25, 2.5, 1), (0x14F, 16.25, 2.5, 1), (0x151, 17.25, 2.5, 1)]
    + [(0x3A, 0, 3.5, 1.75)] + [(0x1E + i, 1.75 + i, 3.5, 1) for i in range(11)]
    + [(0x2B, 12.75, 3.5, 1), (0x1C, 13.75, 3.5, 1.25)]
    + [(0x2A, 0, 4.5, 1.25), (0x56, 1.25, 4.5, 1)] + [(0x2C + i, 2.25 + i, 4.5, 1) for i in range(10)]
    + [(0x36, 12.25, 4.5, 2.75), (0x148, 16.25, 4.5, 1)]
    + [(0x1D, 0, 5.5, 1.25), (0x15B, 1.25, 5.5, 1.25), (0x38, 2.5, 5.5, 1.25), (0x39, 3.75, 5.5, 6.25),
       (0x138, 10, 5.5, 1.25), (0x15C, 11.25, 5.5, 1.25), (0x15D, 12.5, 5.5, 1.25), (0x11D, 13.75, 5.5, 1.25),
       (0x14B, 15.25, 5.5, 1), (0x150, 16.25, 5.5, 1), (0x14D, 17.25, 5.5, 1)]
)
TOUTES_LES_TOUCHES = sorted({code for code, *_ in DISPOSITION} | {0xFFFF1})  # + logo G

# Touches carrées des 4 rangées du milieu, repérées par (rangée 0-3, centre x)
RANGEES_ECRAN = {1.5: 0, 2.5: 1, 3.5: 2, 4.5: 3}
TOUCHES_CARREES = {(RANGEES_ECRAN[y], x + 0.5): code
                   for code, x, y, largeur in DISPOSITION
                   if y in RANGEES_ECRAN and largeur == 1 and x < 15}


def _touches_du_chiffre(chiffre, n):
    """Touches du `chiffre` à la position `n` (0 = chiffre de gauche, 1 = de droite)."""
    position, touches_f = POSITIONS_CHIFFRES[n], TOUCHES_F[n]
    lignes = CHIFFRES[chiffre]
    codes = []
    if len(lignes) == 5:  # la 1re chaîne est la rangée des touches F
        ligne_f = lignes[0][n] if isinstance(lignes[0], tuple) else lignes[0]
        codes += [touches_f[i] for i, p in enumerate(ligne_f) if p == "#"]
        lignes = lignes[1:]
    for rangee, ligne in enumerate(lignes):
        for i, p in enumerate(ligne):
            if p != "#":
                continue
            code = TOUCHES_CARREES.get((rangee, position + DEBUT_RANGEE[rangee] + i))
            if code is None:
                raise ValueError(f"Chiffre {chiffre} : pas de touche rangée {rangee + 1}, case {i + 1}")
            codes.append(code)
    return codes


# Touches de chaque chiffre à chaque position, calculées une fois au démarrage
TOUCHES_CHIFFRES = [{c: _touches_du_chiffre(c, n) for c in CHIFFRES} for n in range(2)]

LOGI_DEVICETYPE_PERKEY_RGB = 4
NOM_EVENEMENT_STOP = "Local\\HorlogeClavierLogitech_Stop"


# ---------------------------------------------------------------------------
# Messages (console, ou boîte de dialogue si lancé avec pythonw)
# ---------------------------------------------------------------------------
def message(texte, erreur=False):
    if sys.stdout is not None:
        print(texte, file=sys.stderr if erreur else sys.stdout)
    else:
        icone = 0x10 if erreur else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, texte, "Horloge clavier Logitech", icone)


# ---------------------------------------------------------------------------
# Accès au SDK LED de G HUB
# ---------------------------------------------------------------------------
class SdkLed:
    def __init__(self):
        bits = "x64" if struct.calcsize("P") == 8 else "x86"
        ici = os.path.dirname(os.path.abspath(__file__))
        candidats = [
            os.path.join(ici, f"sdk_legacy_led_{bits}.dll"),
            rf"C:\Program Files\LGHUB\sdks\sdk_legacy_led_{bits}.dll",
            rf"C:\Program Files\LGHUB\sdk_legacy_led_{bits}.dll",
            os.path.join(ici, "LogitechLedEnginesWrapper.dll"),
        ]
        chemin = next((c for c in candidats if os.path.isfile(c)), None)
        if chemin is None:
            raise RuntimeError("SDK LED introuvable. Installez Logitech G HUB.")
        d = self.dll = ctypes.CDLL(chemin)
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

    def connecter(self, eteindre=True):
        """Prend le contrôle de l'éclairage (et éteint tout le clavier si `eteindre`)."""
        if not self.dll.LogiLedInitWithName(b"Horloge clavier"):
            return False
        time.sleep(0.5)  # laisse G HUB terminer la connexion
        self.dll.LogiLedSetTargetDevice(LOGI_DEVICETYPE_PERKEY_RGB)
        if eteindre:
            self.dll.LogiLedSetLighting(*COULEUR_FOND)
        return True

    def touche(self, code, couleur):
        return self.dll.LogiLedSetLightingForKeyWithKeyName(code, *couleur)

    def deconnecter(self):
        self.dll.LogiLedShutdown()


# ---------------------------------------------------------------------------
# Calcul de l'image
# ---------------------------------------------------------------------------
def attenuer(couleur, intensite):
    # Puissance 2.2 : l'œil perçoit la luminosité des LEDs de façon non linéaire,
    # sans cette correction le fondu paraîtrait brusque au début et lent à la fin.
    facteur = intensite ** 2.2
    return tuple(round(v * facteur) for v in couleur)


def phase(t):
    """Renvoie (afficher_les_heures, intensité 0-1) à l'instant `t` du cycle d'alternance."""
    demi_cycle = DUREE_FONDU + DUREE_AFFICHAGE + DUREE_FONDU
    heures = (t % (2 * demi_cycle)) < demi_cycle
    u = t % demi_cycle
    if u < DUREE_FONDU:
        intensite = u / DUREE_FONDU                      # apparition
    elif u < DUREE_FONDU + DUREE_AFFICHAGE:
        intensite = 1.0
    else:
        intensite = (demi_cycle - u) / DUREE_FONDU       # disparition
    return heures, intensite


def image_pour(moment, t):
    """Couleur de chaque touche : `moment` = l'heure affichée, `t` = temps écoulé (pour le fondu)."""
    image = {code: COULEUR_FOND for code in TOUTES_LES_TOUCHES}

    heures, intensite = phase(t)
    texte, couleur = (f"{moment:%H}", COULEUR_HEURES) if heures else (f"{moment:%M}", COULEUR_MINUTES)
    couleur = attenuer(couleur, intensite)

    # Les deux chiffres, chacun à sa position
    for chiffre, touches in zip(texte, TOUCHES_CHIFFRES):
        for code in touches[chiffre]:
            image[code] = couleur

    # Secondes : la touche en cours s'allume progressivement (9 touches = 60 s)
    progression = (moment.second + moment.microsecond / 1e6) / (60 / len(TOUCHES_SECONDES))
    for i, code in enumerate(TOUCHES_SECONDES):
        niveau = min(1.0, max(0.0, progression - i))
        if niveau > 0:
            image[code] = tuple(round(v * niveau) for v in COULEUR_SECONDES)
    return image


def enregistrer_apercu(chemin, images, echelle=36):
    """Dessine le clavier (géométrie réelle) pour chaque image, empilées dans un PNG."""
    marge = 10
    hauteur_clavier = int(6.5 * echelle) + marge
    w, h = int(18.25 * echelle) + 2 * marge, hauteur_clavier * len(images) + marge
    px = bytearray([18, 18, 22] * (w * h))
    for n, image in enumerate(images):
        dy = n * hauteur_clavier
        for code, x, y, largeur in DISPOSITION:
            c = image.get(code, COULEUR_FOND)
            rgb = bytes((50, 50, 58) if sum(c) == 0 else tuple(min(255, int(v * 2.55)) for v in c))
            x0, x1 = marge + int((x + 0.06) * echelle), marge + int((x + largeur - 0.06) * echelle)
            y0, y1 = marge + dy + int((y + 0.06) * echelle), marge + dy + int((y + 0.94) * echelle)
            for yy in range(y0, y1):
                px[(yy * w + x0) * 3:(yy * w + x1) * 3] = rgb * (x1 - x0)
    brut = b"".join(b"\x00" + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))

    def bloc(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    with open(chemin, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + bloc(b"IDAT", zlib.compress(brut, 9)) + bloc(b"IEND", b""))


# ---------------------------------------------------------------------------
# Envoi au clavier (seules les touches qui changent sont envoyées)
# ---------------------------------------------------------------------------
class Afficheur:
    def __init__(self, sdk):
        self.sdk = sdk
        self.envoye = {}
        self.dernier_complet = 0.0

    def reinitialiser(self):
        """À appeler après chaque reconnexion : l'état des touches n'est plus connu."""
        self.envoye.clear()
        self.dernier_complet = time.monotonic()

    def afficher(self, image):
        if time.monotonic() - self.dernier_complet > RAFRAICHISSEMENT_COMPLET:
            self.dernier_complet = time.monotonic()
            self.envoye.clear()
        for code, couleur in image.items():
            if self.envoye.get(code) != couleur:
                self.sdk.touche(code, couleur)
                self.envoye[code] = couleur


# ---------------------------------------------------------------------------
# Inactivité (dernier appui clavier ou mouvement de souris, d'après Windows)
# ---------------------------------------------------------------------------
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def secondes_inactivite():
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    maintenant = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    return ((maintenant - info.dwTime) & 0xFFFFFFFF) / 1000


# ---------------------------------------------------------------------------
# Lancement / arrêt
# ---------------------------------------------------------------------------
def kernel32():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateEventW.restype = wintypes.HANDLE
    k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k32.OpenEventW.restype = wintypes.HANDLE
    k32.SetEvent.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.WaitForSingleObject.restype = wintypes.DWORD
    return k32


def arreter_instance():
    k32 = kernel32()
    h = k32.OpenEventW(0x0002, False, NOM_EVENEMENT_STOP)  # EVENT_MODIFY_STATE
    if not h:
        message("Aucune horloge clavier en cours d'exécution.")
        return 1
    k32.SetEvent(h)
    k32.CloseHandle(h)
    message("Horloge clavier arrêtée.")
    return 0


def lancer(args):
    k32 = kernel32()
    evenement_stop = k32.CreateEventW(None, True, False, NOM_EVENEMENT_STOP)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        message("L'horloge clavier tourne déjà. Utilisez --stop pour l'arrêter.", erreur=True)
        return 1

    try:
        sdk = SdkLed()
    except (RuntimeError, OSError) as e:
        message(str(e), erreur=True)
        return 1
    # Vérifie dès le lancement que G HUB répond, sans toucher à l'éclairage.
    if not sdk.connecter(eteindre=False):
        message("Impossible de se connecter à G HUB.\n\n"
                "Vérifiez que G HUB est lancé et que l'option « Autoriser les jeux et "
                "applications à contrôler mon éclairage » est activée dans ses paramètres.",
                erreur=True)
        return 1

    afficheur = Afficheur(sdk)
    connecte = True  # vrai tant que l'horloge a la main sur l'éclairage

    def arret_demande(ms=INTERVALLE_MS):
        return k32.WaitForSingleObject(evenement_stop, ms) == 0

    try:
        if args.demo:
            sdk.dll.LogiLedSetLighting(*COULEUR_FOND)
            cycle = 2 * (2 * DUREE_FONDU + DUREE_AFFICHAGE)
            aujourdhui = dt.date.today()
            for h, m in [(13, 37), (20, 8), (9, 53)]:
                base = dt.datetime.combine(aujourdhui, dt.time(h, m))
                print(f"  démo : {h:02d}:{m:02d}", flush=True)
                debut = time.monotonic()
                while (ecoule := time.monotonic() - debut) < cycle:
                    afficheur.afficher(image_pour(base + dt.timedelta(seconds=ecoule * 5), ecoule))
                    if arret_demande():
                        return 0
            return 0

        # Rend la main à G HUB : l'horloge n'apparaîtra qu'après le délai d'inactivité.
        sdk.deconnecter()
        connecte = False
        if sys.stdout is not None:
            print(f"Horloge clavier lancée : elle s'affiche après {args.delai:g} s d'inactivité.\n"
                  "Ctrl+C (ou « --stop ») pour arrêter.")
        debut = 0.0
        prochain_essai = 0.0
        while True:
            inactif = secondes_inactivite() >= args.delai
            if inactif and not connecte and time.monotonic() >= prochain_essai:
                connecte = sdk.connecter()
                if connecte:
                    afficheur.reinitialiser()
                    debut = time.monotonic()  # le cycle commence par l'apparition des heures
                else:
                    prochain_essai = time.monotonic() + 10  # G HUB indisponible : on réessaie plus tard
            elif not inactif and connecte:
                sdk.deconnecter()  # activité : G HUB reprend immédiatement son éclairage
                connecte = False

            if connecte:
                afficheur.afficher(image_pour(dt.datetime.now(), time.monotonic() - debut))
            if arret_demande(INTERVALLE_MS if connecte else INTERVALLE_VEILLE_MS):
                return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if connecte:
            sdk.deconnecter()  # G HUB reprend l'éclairage du profil actif
        k32.CloseHandle(evenement_stop)


def main():
    p = argparse.ArgumentParser(description="Affiche l'heure sur un clavier Logitech G.")
    p.add_argument("--stop", action="store_true", help="arrête l'horloge lancée en arrière-plan")
    p.add_argument("--demo", action="store_true", help="montre quelques heures de test")
    p.add_argument("--delai", type=float, default=DELAI_INACTIVITE, metavar="SECONDES",
                   help=f"inactivité avant l'affichage de l'horloge (défaut {DELAI_INACTIVITE} s)")
    p.add_argument("--apercu", nargs="?", const="apercu.png", metavar="FICHIER.png",
                   help="enregistre une image du clavier (heures, fondu, minutes)")
    args = p.parse_args()

    if args.apercu:
        maintenant = dt.datetime.now()
        milieu_fondu = DUREE_FONDU + DUREE_AFFICHAGE + DUREE_FONDU / 2
        moments = [1.0, milieu_fondu, milieu_fondu + DUREE_FONDU + 1.0]  # heures, fondu, minutes
        enregistrer_apercu(args.apercu, [image_pour(maintenant, t) for t in moments])
        print(f"Aperçu enregistré : {os.path.abspath(args.apercu)}")
        return
    sys.exit(arreter_instance() if args.stop else lancer(args))


if __name__ == "__main__":
    main()
