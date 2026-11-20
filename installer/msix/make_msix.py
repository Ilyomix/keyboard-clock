"""Builds the Microsoft Store package (MSIX) from the PyInstaller app in dist/KeyboardClock.

    python installer/msix/make_msix.py 0.2.0

The Store signs the package itself, so a Store install never meets SmartScreen. The package identity comes
from Partner Center (Product management > Product identity) through environment variables:
    MSIX_IDENTITY_NAME   e.g. 12345Ilyomix.KeyboardClock
    MSIX_PUBLISHER       e.g. CN=ABCD1234-...
    MSIX_PUBLISHER_NAME  e.g. Ilyomix
Without them, placeholders are used: the package builds and can be checked, but the Store would refuse it.

Writes build/msix/ (the layout) and dist/KeyboardClock.msix (unsigned, for the Store). Needs makeappx.exe from
the Windows SDK (on GitHub's windows-latest runners).
"""
import glob
import os
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
import keyboard_clock as kc  # noqa: E402  (the app draws its own icon)

LANGS = {"en": "en-us", "fr": "fr-fr", "es": "es-es", "de": "de-de", "it": "it-it", "pt": "pt-br"}
LOGOS = {"StoreLogo.png": 50, "Square44x44Logo.png": 44, "Square71x71Logo.png": 71, "Square150x150Logo.png": 150,
         "Square310x310Logo.png": 310, "Square44x44Logo.targetsize-256.png": 256,
         "Square44x44Logo.targetsize-48.png": 48, "Square44x44Logo.targetsize-24.png": 24,
         "Square44x44Logo.targetsize-16.png": 16}

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap desktop rescap">
  <Identity Name="{name}" Publisher="{publisher}" Version="{version}" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>Keyboard Clock</DisplayName>
    <PublisherDisplayName>{publisher_name}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
{resources}
  </Resources>
  <Applications>
    <Application Id="KeyboardClock" Executable="KeyboardClock.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="Keyboard Clock" Description="{description}" BackgroundColor="transparent"
                          Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Square71x71Logo="Assets\\Square71x71Logo.png" Square310x310Logo="Assets\\Square310x310Logo.png" />
      </uap:VisualElements>
      <Extensions>
        <!-- Starts with Windows (the user turns it off in Settings > Apps > Startup). This copy of the app starts
             in the background, without its window. -->
        <desktop:Extension Category="windows.startupTask" Executable="KeyboardClockBackground.exe"
                           EntryPoint="Windows.FullTrustApplication">
          <desktop:StartupTask TaskId="KeyboardClockStartup" Enabled="true" DisplayName="Keyboard Clock" />
        </desktop:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def logo(path, size):
    bgra = kc.icon_pixels(size)
    rgba = bytearray(len(bgra))
    rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = bgra[2::4], bgra[1::4], bgra[0::4], bgra[3::4]
    with open(path, "wb") as f:
        f.write(kc.png_bytes(size, size, rgba))


def makeappx():
    found = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\makeappx.exe"))
    if not found:
        sys.exit("makeappx.exe not found (Windows SDK)")
    return found[-1]


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python installer/msix/make_msix.py VERSION")
    numbers = [int(n) for n in sys.argv[1].split("-")[0].split(".")][:3]
    version = ".".join(str(n) for n in numbers + [0] * (3 - len(numbers))) + ".0"   # the Store wants x.y.z.0
    app = os.path.join(ROOT, "dist", "KeyboardClock")
    out = os.path.join(ROOT, "build", "msix")
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(app, out)
    shutil.copy(os.path.join(out, "KeyboardClock.exe"), os.path.join(out, "KeyboardClockBackground.exe"))
    os.makedirs(os.path.join(out, "Assets"))
    for name, size in LOGOS.items():
        logo(os.path.join(out, "Assets", name), size)
    resources = "\n".join(f'    <Resource Language="{tag}" />' for tag in LANGS.values())
    manifest = MANIFEST.format(
        name=escape(os.environ.get("MSIX_IDENTITY_NAME") or "Ilyomix.KeyboardClock"),
        publisher=escape(os.environ.get("MSIX_PUBLISHER") or "CN=Ilyomix"),
        publisher_name=escape(os.environ.get("MSIX_PUBLISHER_NAME") or "Ilyomix"),
        version=version, resources=resources,
        description=escape("The time in big digits on your RGB keyboard while you are away"))
    with open(os.path.join(out, "AppxManifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)
    target = os.path.join(ROOT, "dist", "KeyboardClock.msix")
    subprocess.run([makeappx(), "pack", "/d", out, "/p", target, "/o"], check=True)
    print(f"{target} ({version})")


if __name__ == "__main__":
    main()
