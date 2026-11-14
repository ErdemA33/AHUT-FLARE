; AHUT FLARE — Inno Setup kurulum betiği
; Derlemek için: Inno Setup 6 kurulu olmalı. exe_olustur.bat bunu kendisi çağırır.
; Elle: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" paketleme\kurulum.iss

#define UygAdi      "AHUT FLARE"
#define UygSurum    "1.0.0"
#define UygYayinci  "AHUT - Ankara Havacilik ve Uzay Teknolojileri Hackathon Takimi"
#define UygExe      "AHUT FLARE.exe"

[Setup]
AppId={{7C4E91D8-2B6A-4F35-9E07-A14F1A2E0001}
AppName={#UygAdi}
AppVersion={#UygSurum}
AppVerName={#UygAdi} {#UygSurum}
AppPublisher={#UygYayinci}
DefaultDirName={autopf}\{#UygAdi}
DefaultGroupName={#UygAdi}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=Cikti
OutputBaseFilename=AHUT-FLARE-Kurulum
SetupIconFile=..\arayuz\marka\ahut.ico
UninstallDisplayIcon={app}\{#UygExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "turkce"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "masaustu"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "dosyaturu"; Description: "AHUT vaka dosyalarini (.ahut) bu programla ac"; GroupDescription: "Dosya turleri:"

[Files]
; GIZLILIK: evren_anahtar.txt kurulum paketine ASLA konulmaz. Herkes kendi
; anahtarini %LOCALAPPDATA%\AHUT FLARE\ altina kendisi koyar (bkz. BENIOKU.txt).
Source: "..\dist\AHUT FLARE\*"; DestDir: "{app}"; Excludes: "evren_anahtar.txt,*.anahtar"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{localappdata}\{#UygAdi}"
Name: "{localappdata}\{#UygAdi}\veri"
Name: "{localappdata}\{#UygAdi}\veri\vakalar"
Name: "{localappdata}\{#UygAdi}\render"

[Icons]
Name: "{group}\{#UygAdi}"; Filename: "{app}\{#UygExe}"
Name: "{group}\{#UygAdi} - Render klasoru"; Filename: "{localappdata}\{#UygAdi}\render"
Name: "{group}\{cm:UninstallProgram,{#UygAdi}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#UygAdi}"; Filename: "{app}\{#UygExe}"; Tasks: masaustu

[Registry]
Root: HKA; Subkey: "Software\Classes\.ahut"; ValueType: string; ValueName: ""; ValueData: "AHUTFlare.Vaka"; Flags: uninsdeletevalue; Tasks: dosyaturu
Root: HKA; Subkey: "Software\Classes\AHUTFlare.Vaka"; ValueType: string; ValueName: ""; ValueData: "AHUT FLARE vaka dosyasi"; Flags: uninsdeletekey; Tasks: dosyaturu
Root: HKA; Subkey: "Software\Classes\AHUTFlare.Vaka\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#UygExe},0"; Tasks: dosyaturu
Root: HKA; Subkey: "Software\Classes\AHUTFlare.Vaka\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#UygExe}"" ""%1"""; Tasks: dosyaturu

[Run]
Filename: "{app}\{#UygExe}"; Description: "{cm:LaunchProgram,{#UygAdi}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; Kullanici verisi (kayitli vakalar, profil) SILINMEZ; {localappdata} dokunulmaz.
