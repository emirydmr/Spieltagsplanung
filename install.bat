@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion
title WFV Spieltagsplaner – Installation
color 0F

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║     WFV Spieltagsplaner – Installation           ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: ─── Zielordner ─────────────────────────────────────────────
set "INSTALL_DIR=%USERPROFILE%\Spieltagsplaner"
set "REPO_URL=https://github.com/emirydmr/Spieltagsplanung/archive/refs/heads/main.zip"

:: ─── Prüfe ob Python installiert ist ────────────────────────
set "PYTHON_CMD="
where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
) else (
    where python3 >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=python3"
    )
)

if not defined PYTHON_CMD (
    echo  [!] Python ist nicht installiert.
    echo      Installiere Python 3.13...
    echo.
    
    :: Lade Python 3.13 Installer herunter
    set "PY_INSTALLER=%TEMP%\python-3.13-installer.exe"
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe' -OutFile '%TEMP%\python-3.13-installer.exe'"
    
    if not exist "!PY_INSTALLER!" (
        echo  [X] Python-Download fehlgeschlagen!
        pause
        exit /b 1
    )
    
    echo  Installiere Python (dies dauert ca. 1-2 Minuten)...
    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
    
    :: PATH aktualisieren
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python313\;%LOCALAPPDATA%\Programs\Python\Python313\Scripts\;%PATH%"
    set "PYTHON_CMD=python"
    
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo  [X] Python-Installation fehlgeschlagen!
        echo      Bitte Python manuell installieren: https://www.python.org
        pause
        exit /b 1
    )
    echo  [OK] Python installiert.
)

echo  Python: gefunden
echo.

:: ─── Repository herunterladen ───────────────────────────────
if exist "%INSTALL_DIR%\src\api\server.py" (
    echo  Projekt existiert bereits – aktualisiere...
    set "ZIP_FILE=%TEMP%\spieltagsplaner.zip"
    set "EXTRACT_DIR=%TEMP%\spieltagsplaner_extract"
    
    powershell -Command "Invoke-WebRequest -Uri '%REPO_URL%' -OutFile '!ZIP_FILE!'"
    if not exist "!ZIP_FILE!" (
        echo  [X] Download fehlgeschlagen!
        pause
        exit /b 1
    )
    
    if exist "!EXTRACT_DIR!" rmdir /s /q "!EXTRACT_DIR!"
    powershell -Command "Expand-Archive -Path '!ZIP_FILE!' -DestinationPath '!EXTRACT_DIR!' -Force"
    
    :: Kopiere neue Dateien ueber bestehende (ohne .venv und output zu ueberschreiben)
    robocopy "!EXTRACT_DIR!\Spieltagsplanung-main" "%INSTALL_DIR%" /e /xd .venv output spielplan_logs /xf *.lnk >nul 2>nul
    
    rmdir /s /q "!EXTRACT_DIR!" 2>nul
    del "!ZIP_FILE!" 2>nul
    echo  [OK] Aktualisiert.
) else (
    echo  Lade Projekt herunter...
    set "ZIP_FILE=%TEMP%\spieltagsplaner.zip"
    set "EXTRACT_DIR=%TEMP%\spieltagsplaner_extract"
    
    powershell -Command "Invoke-WebRequest -Uri '%REPO_URL%' -OutFile '!ZIP_FILE!'"
    if not exist "!ZIP_FILE!" (
        echo  [X] Download fehlgeschlagen! Pruefe die Internetverbindung.
        pause
        exit /b 1
    )
    
    if exist "!EXTRACT_DIR!" rmdir /s /q "!EXTRACT_DIR!"
    powershell -Command "Expand-Archive -Path '!ZIP_FILE!' -DestinationPath '!EXTRACT_DIR!' -Force"
    
    :: GitHub ZIP enthaelt Unterordner "Spieltagsplanung-main" – verschiebe Inhalt
    if exist "!EXTRACT_DIR!\Spieltagsplanung-main" (
        move "!EXTRACT_DIR!\Spieltagsplanung-main" "%INSTALL_DIR%" >nul
    ) else (
        echo  [X] Entpacken fehlgeschlagen!
        pause
        exit /b 1
    )
    
    rmdir /s /q "!EXTRACT_DIR!" 2>nul
    del "!ZIP_FILE!" 2>nul
    echo  [OK] Projekt heruntergeladen.
)
echo.

cd /d "%INSTALL_DIR%"

:: ─── Virtuelle Umgebung erstellen ───────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo  Erstelle virtuelle Umgebung...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo  [X] venv-Erstellung fehlgeschlagen!
        pause
        exit /b 1
    )
    echo  [OK] Virtuelle Umgebung erstellt.
) else (
    echo  [OK] Virtuelle Umgebung vorhanden.
)
echo.

:: ─── Pakete installieren ────────────────────────────────────
echo  Installiere Pakete (dies dauert beim ersten Mal ca. 2-3 Minuten)...
.venv\Scripts\pip.exe install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo  [X] Paketinstallation fehlgeschlagen!
    pause
    exit /b 1
)
echo  [OK] Alle Pakete installiert.
echo.

:: ─── App-Icon erstellen ─────────────────────────────────────
set "LOGO_JPG=%INSTALL_DIR%\ui\assets\wfv-logo.jpg"
set "ICO_FILE=%INSTALL_DIR%\ui\assets\app.ico"

if not exist "%ICO_FILE%" (
    echo  Erstelle App-Icon...
    powershell -Command "& { Add-Type -AssemblyName System.Drawing; $img = [System.Drawing.Image]::FromFile('%LOGO_JPG%'); $bmp = New-Object System.Drawing.Bitmap($img, 64, 64); $ms = New-Object System.IO.MemoryStream; $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); $pngBytes = $ms.ToArray(); $ms.Close(); $bmp.Dispose(); $img.Dispose(); $icoStream = New-Object System.IO.FileStream('%ICO_FILE%', [System.IO.FileMode]::Create); $bw = New-Object System.IO.BinaryWriter($icoStream); $bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]1); $bw.Write([byte]64); $bw.Write([byte]64); $bw.Write([byte]0); $bw.Write([byte]0); $bw.Write([UInt16]0); $bw.Write([UInt16]32); $bw.Write([UInt32]$pngBytes.Length); $bw.Write([UInt32]22); $bw.Write($pngBytes); $bw.Close(); $icoStream.Close() }" 2>nul
    if exist "%ICO_FILE%" (
        echo  [OK] App-Icon erstellt.
    )
)

:: ─── Desktop-Verknüpfung ────────────────────────────────────
echo  Erstelle Desktop-Verknuepfung...
set "SHORTCUT=%USERPROFILE%\Desktop\Spieltagsplaner.lnk"
set "LAUNCHER=%INSTALL_DIR%\launcher.pyw"

powershell -Command "& { $ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%INSTALL_DIR%\.venv\Scripts\pythonw.exe'; $sc.Arguments = '\"%LAUNCHER%\"'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.Description = 'WFV Spieltagsplaner starten'; $sc.WindowStyle = 1; if (Test-Path '%ICO_FILE%') { $sc.IconLocation = '%ICO_FILE%' }; $sc.Save() }"

if exist "%SHORTCUT%" (
    echo  [OK] Desktop-Verknuepfung erstellt.
) else (
    echo  [!] Verknuepfung konnte nicht erstellt werden.
)

:: ─── Fertig ─────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║     Installation abgeschlossen!                   ║
echo  ║                                                    ║
echo  ║     Starte den Spieltagsplaner ueber die           ║
echo  ║     Desktop-Verknuepfung "Spieltagsplaner"        ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Installationsordner: %INSTALL_DIR%
echo.

:: Frage ob direkt starten
set /p STARTEN="  Jetzt starten? (j/n): "
if /i "%STARTEN%"=="j" (
    start "" "%INSTALL_DIR%\.venv\Scripts\pythonw.exe" "%LAUNCHER%"
)

pause
