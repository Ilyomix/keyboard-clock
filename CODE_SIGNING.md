# Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

> [!NOTE]
> **Not active yet.** Keyboard Clock's Windows files are signed from the first release built after SignPath Foundation accepts the project. Until then they are unsigned, and Windows SmartScreen may say *Windows protected your PC*: click *More info → Run anyway*, or install Keyboard Clock from the Microsoft Store, which Microsoft signs. Every file can still be checked against the `SHA256SUMS.txt` of its release.

## Signed files

Every Windows file of a release is built from this repository by the [release workflow](.github/workflows/release.yml), on GitHub-hosted runners, and signed:

| File | What it is |
|---|---|
| `KeyboardClockSetup.exe` | The installer |
| `KeyboardClock.exe`, `keyboard-clock-cli.exe`, `unins000.exe` | The app, its command line and its uninstaller, as installed by `KeyboardClockSetup.exe` |
| `KeyboardClockPortable.exe`, `keyboard-clock.exe` | The portable app and command line |

Not signed by this project: `keyboard_clock.py` and the Python wheel (Python files carry no Windows signature, check them against `SHA256SUMS.txt`), the open-source Python runtime files that PyInstaller packs inside the app, and the Microsoft Store package, which Microsoft signs.

## How a release gets signed

1. A version tag (`v1.2.3`) starts the [release workflow](.github/workflows/release.yml).
2. It builds the apps and sends them to SignPath, then builds the installer from the signed apps and sends it too. The files SignPath accepts are listed in [installer/signpath](installer/signpath): each must carry the product name `Keyboard Clock` and the version of the release.
3. SignPath checks that the files come from a run of this workflow on this repository.
4. An approver approves each signing request in SignPath. Nothing is signed without that approval.
5. The workflow checks the signatures, installs and uninstalls the signed build, then publishes the release and its `SHA256SUMS.txt`.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [Ilyomix](https://github.com/Ilyomix) |
| Approvers | [Ilyomix](https://github.com/Ilyomix) |

Changes from anyone else arrive as pull requests, which a committer reviews before merging. Team members use multi-factor authentication on GitHub and SignPath.

## Privacy

Keyboard Clock has no telemetry and collects no personal data. The only request it makes on its own is a daily update check on GitHub, which can be turned off in the installer and in the app. Everything else stays on your PC. Details in the [privacy policy](PRIVACY.md).

## Check a file

Right-click the file, then *Properties → Digital Signatures*: the signer is *SignPath Foundation*. Or in PowerShell:

```powershell
Get-AuthenticodeSignature .\KeyboardClockSetup.exe | Format-List Status, SignerCertificate
Get-FileHash .\KeyboardClockSetup.exe   # compare with SHA256SUMS.txt of the release
```

A signed file that doesn't come from this repository's releases is not Keyboard Clock: please [report it](https://github.com/Ilyomix/keyboard-clock/issues).
