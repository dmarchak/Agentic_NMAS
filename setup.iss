; Inno Setup Script for Python App
[Setup]

AppName=Final Project - Dustin Marchak
AppVersion=1.0
DefaultDirName=C:\Users\dmarc\OneDrive\Desktop\Final Project - Dustin Marchak
DefaultGroupName=Final Project - Dustin Marchak
OutputDir=.
OutputBaseFilename=FinalProjectSetup
Compression=lzma
SolidCompression=yes


[Files]
Source: "app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "modules\*"; DestDir: "{app}\modules"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bundle Python embeddable distribution (download and place python-3.x.x-embed-amd64.zip in project folder)
Source: "python-3.x.x-embed-amd64.zip"; DestDir: "{app}\python"; Flags: ignoreversion unpack


[Icons]
Name: "{group}\Final Project"; Filename: "{app}\python\python.exe"; Parameters: "\"{app}\\app.py\""; WorkingDir: "{app}"; IconFilename: "{app}\python\python.exe"
Name: "{userdesktop}\Final Project"; Filename: "{app}\python\python.exe"; Parameters: "\"{app}\\app.py\""; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\python\python.exe"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"


[Run]
Filename: "{app}\python\python.exe"; Parameters: "\"{app}\\app.py\""; Description: "Run Final Project"; Flags: postinstall skipifsilent
