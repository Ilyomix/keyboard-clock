; Keyboard Clock Windows installer (Inno Setup 6.3+). Built by .github/workflows/release.yml:
;   ISCC /DMyAppVersion=1.2.3 installer\keyboard_clock.iss
; Expects dist\KeyboardClock\ (PyInstaller --onedir, no console) and dist\keyboard-clock.exe (command line).
; Code-signed releases add /DSignedUninstaller (see CODE_SIGNING.md).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{ED7F7D37-CD5B-4814-94B7-A66979C1F788}
AppName=Keyboard Clock
AppVersion={#MyAppVersion}
AppVerName=Keyboard Clock {#MyAppVersion}
AppPublisher=Ilyomix
AppPublisherURL=https://github.com/Ilyomix/keyboard-clock
AppSupportURL=https://github.com/Ilyomix/keyboard-clock/issues
AppUpdatesURL=https://github.com/Ilyomix/keyboard-clock/releases
AppComments=The time in big digits on your RGB keyboard while you are away
DefaultDirName={autopf}\Keyboard Clock
DisableDirPage=auto
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=KeyboardClockSetup
SetupIconFile=..\assets\keyboard-clock.ico
UninstallDisplayIcon={app}\KeyboardClock.exe
UninstallDisplayName=Keyboard Clock
ShowLanguageDialog=auto
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; Code signing (SignPath Foundation) requires the product name and version on every signed file
VersionInfoVersion={#MyAppVersion}
VersionInfoTextVersion={#MyAppVersion}
VersionInfoProductName=Keyboard Clock
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductTextVersion={#MyAppVersion}
VersionInfoCompany=Ilyomix
VersionInfoCopyright=Copyright (c) 2026 Ilyomix. MIT License.
VersionInfoDescription=Keyboard Clock installer
#ifdef SignedUninstaller
; A first compile writes the uninstaller to build\uninstaller and stops. Once that file is signed (together with the
; apps), the second compile embeds its signature, so the installed unins000.exe is signed too.
SignedUninstaller=yes
SignedUninstallerDir=..\build\uninstaller
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[CustomMessages]
; English is the default for every language; the lines below override it
Comment=The time in big digits on your RGB keyboard while you are away
GHub=Tip: in Logitech G HUB, open Settings and turn on "Allow games & applications to control my lighting", so Keyboard Clock can light your keys.
UpdatesGroup=Updates:
CheckUpdates=Check for a new version once a day (asks GitHub; only the Keyboard Clock version is sent)
french.Comment=L'heure en gros chiffres sur votre clavier RGB quand vous vous absentez
french.GHub=Astuce : dans Logitech G HUB, ouvrez les Paramètres et activez « Autoriser les jeux et applications à contrôler mon éclairage », pour que Keyboard Clock puisse allumer vos touches.
french.UpdatesGroup=Mises à jour :
french.CheckUpdates=Rechercher une nouvelle version une fois par jour (sur GitHub ; seule la version de Keyboard Clock est envoyée)
spanish.Comment=La hora en grandes dígitos en tu teclado RGB mientras no estás
spanish.GHub=Consejo: en Logitech G HUB, abre Configuración y activa «Permitir que los juegos y aplicaciones controlen mi iluminación», para que Keyboard Clock pueda iluminar tus teclas.
spanish.UpdatesGroup=Actualizaciones:
spanish.CheckUpdates=Buscar una nueva versión una vez al día (en GitHub; solo se envía la versión de Keyboard Clock)
german.Comment=Die Uhrzeit in großen Ziffern auf deiner RGB-Tastatur, während du weg bist
german.GHub=Tipp: Öffne in Logitech G HUB die Einstellungen und aktiviere „Spielen und Anwendungen erlauben, meine Beleuchtung zu steuern“, damit Keyboard Clock deine Tasten beleuchten kann.
german.UpdatesGroup=Updates:
german.CheckUpdates=Einmal täglich nach einer neuen Version suchen (auf GitHub; nur die Keyboard-Clock-Version wird gesendet)
italian.Comment=L'ora in grandi cifre sulla tua tastiera RGB mentre sei via
italian.GHub=Suggerimento: in Logitech G HUB apri Impostazioni e attiva «Consenti a giochi e applicazioni di controllare la mia illuminazione», così Keyboard Clock può illuminare i tuoi tasti.
italian.UpdatesGroup=Aggiornamenti:
italian.CheckUpdates=Cercare una nuova versione una volta al giorno (su GitHub; viene inviata solo la versione di Keyboard Clock)
brazilianportuguese.Comment=A hora em dígitos grandes no seu teclado RGB enquanto você está fora
brazilianportuguese.GHub=Dica: no Logitech G HUB, abra Configurações e ative “Permitir que jogos e aplicativos controlem minha iluminação”, para que o Keyboard Clock possa acender suas teclas.
brazilianportuguese.UpdatesGroup=Atualizações:
brazilianportuguese.CheckUpdates=Procurar uma nova versão uma vez por dia (no GitHub; só a versão do Keyboard Clock é enviada)
portuguese.Comment=A hora em dígitos grandes no seu teclado RGB enquanto está ausente
portuguese.GHub=Dica: no Logitech G HUB, abra as Definições e ative “Permitir que jogos e aplicações controlem a minha iluminação”, para que o Keyboard Clock possa acender as suas teclas.
portuguese.UpdatesGroup=Atualizações:
portuguese.CheckUpdates=Procurar uma nova versão uma vez por dia (no GitHub; apenas é enviada a versão do Keyboard Clock)

[Tasks]
Name: "autostart"; Description: "{cm:AutoStartProgram,Keyboard Clock}"; GroupDescription: "{cm:AutoStartProgramGroupDescription}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Shown during installation as SignPath Foundation's terms ask for anything that contacts a server (PRIVACY.md)
Name: "checkupdates"; Description: "{cm:CheckUpdates}"; GroupDescription: "{cm:UpdatesGroup}"

[Files]
Source: "..\dist\KeyboardClock\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\keyboard-clock.exe"; DestDir: "{app}"; DestName: "keyboard-clock-cli.exe"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Keyboard Clock"; Filename: "{app}\KeyboardClock.exe"; Comment: "{cm:Comment}"; AppUserModelID: "Ilyomix.KeyboardClock"
Name: "{autodesktop}\Keyboard Clock"; Filename: "{app}\KeyboardClock.exe"; Comment: "{cm:Comment}"; Tasks: desktopicon

[Registry]
; Same value the app's "Start with Windows" toggles
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KeyboardClock"; ValueData: """{app}\KeyboardClock.exe"" --background --from-autostart"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
; Saves the "check for updates" box. Silent installs (in-app updates) keep the setting as it is.
Filename: "{app}\keyboard-clock-cli.exe"; Parameters: "--check-updates {code:UpdateChecksSwitch}"; Flags: runhidden runasoriginaluser waituntilterminated; Check: InteractiveInstall
Filename: "{app}\KeyboardClock.exe"; Description: "{cm:LaunchProgram,Keyboard Clock}"; Flags: nowait postinstall skipifsilent
; In-app updates run this installer silently with /RELAUNCH=1: start the new version afterwards
Filename: "{app}\KeyboardClock.exe"; Parameters: "--after-update"; Flags: nowait; Check: ShouldRelaunch

[UninstallRun]
; Stops Keyboard Clock (G HUB takes the lighting back) and removes the startup entry, settings and logs
Filename: "{app}\KeyboardClock.exe"; Parameters: "--uninstall"; RunOnceId: "KeyboardClockCleanup"; Flags: runhidden waituntilterminated

[Code]
var
  UpdateTaskShown: Boolean;

function ShouldRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

function InteractiveInstall: Boolean;
begin
  Result := not WizardSilent;
end;

{ Keyboard Clock writes settings.json with Python's json module: "key": value }
function UpdateChecksOff: Boolean;
var
  Settings: AnsiString;
begin
  Result := LoadStringFromFile(ExpandConstant('{localappdata}\KeyboardClock\settings.json'), Settings) and
    (Pos('"check_updates": false', String(Settings)) > 0);
end;

function UpdateChecksSwitch(Param: String): String;
begin
  if WizardIsTaskSelected('checkupdates') then
    Result := 'on'
  else
    Result := 'off';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  { An older Keyboard Clock may be running: ask it to give the lighting back and quit before files are replaced }
  if FileExists(ExpandConstant('{app}\KeyboardClock.exe')) then
  begin
    Exec(ExpandConstant('{app}\KeyboardClock.exe'), '--stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { The box shows the current setting the first time the page appears: it may have been turned off in the app }
  if (CurPageID = wpSelectTasks) and not UpdateTaskShown then
  begin
    UpdateTaskShown := True;
    if UpdateChecksOff then
      WizardSelectTasks('!checkupdates');
  end;
  if CurPageID = wpFinished then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + CustomMessage('GHub');
end;
