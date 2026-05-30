[Setup]
AppName=egbtheme-creator
AppVersion=0.8.0
DefaultDirName={autopf}\egbtheme-creator
DefaultGroupName=egbtheme-creator
UninstallDisplayIcon={app}\egbtheme-creator.exe
SetupIconFile=es_theme_editor.ico
Compression=lzma2
SolidCompression=yes
OutputDir=.
OutputBaseFilename=egbtheme-creator_installer

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "dist\egbtheme-creator\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\egbtheme-creator"; Filename: "{app}\egbtheme-creator.exe"
Name: "{group}\Desinstalar"; Filename: "{uninstallexe}"
Name: "{commondesktop}\egbtheme-creator"; Filename: "{app}\egbtheme-creator.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos adicionales:"

[Run]
Filename: "{app}\egbtheme-creator.exe"; Description: "Ejecutar egbtheme-creator ahora"; Flags: postinstall nowait skipifsilent