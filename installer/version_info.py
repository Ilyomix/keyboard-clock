"""Windows version resources for Keyboard Clock's .exe files (PyInstaller --version-file).

Code signing through SignPath Foundation requires every signed file to carry the product name and the
product version, the same for all files of a release (see CODE_SIGNING.md).

    python installer/version_info.py 0.2.0 build/version   ->  build/version/app.txt, portable.txt, cli.txt
"""
import os
import re
import sys

PRODUCT = "Keyboard Clock"
EXES = [  # (output file, exe name, description shown by Windows in file properties and Task Manager)
    ("app.txt", "KeyboardClock", "Keyboard Clock"),                    # installed app (PyInstaller --onedir)
    ("portable.txt", "KeyboardClockPortable", "Keyboard Clock"),        # portable app
    ("cli.txt", "keyboard-clock", "Keyboard Clock command line"),        # keyboard-clock-cli.exe once installed
]


def version_info(name, description, version):
    numbers = [int(n) for n in re.findall(r"\d+", re.split(r"[-+]", version)[0])][:4]
    numbers = tuple(numbers + [0] * (4 - len(numbers)))
    strings = {
        "CompanyName": "Ilyomix",
        "FileDescription": description,
        "FileVersion": version,
        "InternalName": name,
        "LegalCopyright": "Copyright (c) 2026 Ilyomix. MIT License.",
        "OriginalFilename": name + ".exe",
        "ProductName": PRODUCT,
        "ProductVersion": version,
    }
    table = ",\n        ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3F, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        {table}])]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
  ]
)
"""


def main():
    if len(sys.argv) != 3 or not re.match(r"\d+(\.\d+){0,3}([-+].*)?$", sys.argv[1]):
        sys.exit("usage: python installer/version_info.py VERSION OUTPUT_DIR   (VERSION like 0.2.0)")
    version, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for filename, name, description in EXES:
        with open(os.path.join(out, filename), "w", encoding="utf-8") as f:
            f.write(version_info(name, description, version))
    print(f"Version resources for {version} written to {out}")


if __name__ == "__main__":
    main()
