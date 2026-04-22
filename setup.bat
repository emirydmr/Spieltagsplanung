@echo off
chcp 65001 >nul
title Spieltagsplaner – Installation
color 0F

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║      Spieltagsplaner – Ersteinrichtung           ║
echo  ║      WFV Bezirk Franken                          ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: ─── Prüfe ob Python installiert ist ─────────────────────
set "PYTHON="

:: 1. Prüfe ob schon ein venv existiert
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    echo  [OK] Virtuelle Umgebung gefunden.
    goto :HAVE_PYTHON
)

:: 2. Prüfe System-Python
where python >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PYVER=%%i"
    echo  [OK] %PYVER% gefunden.
    set "PYTHON=python"
    goto :SETUP_VENV
)

:: 3. Prüfe py launcher
where py >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%i in ('py --version 2^>^&1') do set "PYVER=%%i"
    echo  [OK] %PYVER% gefunden (py launcher).
    set "PYTHON=py"
    goto :SETUP_VENV
)

:: 4. Python nicht gefunden → automatisch installieren
echo.
echo  [!] Python wurde nicht gefunden.
echo      Python wird jetzt automatisch heruntergeladen und installiert...
echo.

:: Python 3.13 Installer herunterladen
set "PY_URL=https://www.python.org/ftp/python/3.13.3/python-3.13.3-amd64.exe"
set "PY_INSTALLER=%TEMP%\python_installer.exe"

echo  Lade Python herunter...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%' }"

if not exist "%PY_INSTALLER%" (
    echo.
    echo  [FEHLER] Download fehlgeschlagen.
    echo  Bitte Python manuell installieren: https://www.python.org/downloads/
    echo  Wichtig: Bei der Installation "Add Python to PATH" anhaken!
    echo.
    pause
    exit /b 1
)

echo  Installiere Python (das kann einen Moment dauern)...
"%PY_INSTALLER%" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=1

:: Warte kurz bis PATH aktualisiert ist
timeout /t 3 /nobreak >nul

:: Aktualisiere PATH für diese Session
for /f "tokens=*" %%i in ('powershell -Command "[Environment]::GetEnvironmentVariable('Path','User')"') do set "PATH=%%i;%PATH%"

where python >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=python"
    echo  [OK] Python erfolgreich installiert.
) else (
    where py >nul 2>&1
    if %errorlevel%==0 (
        set "PYTHON=py"
        echo  [OK] Python erfolgreich installiert.
    ) else (
        echo.
        echo  [FEHLER] Python Installation fehlgeschlagen.
        echo  Bitte PC neu starten und setup.bat erneut ausfuehren,
        echo  oder Python manuell installieren: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

del "%PY_INSTALLER%" 2>nul

:: ─── Virtuelle Umgebung erstellen ────────────────────────
:SETUP_VENV
echo.
echo  Erstelle virtuelle Umgebung...
%PYTHON% -m venv "%~dp0.venv"
if %errorlevel% neq 0 (
    echo  [FEHLER] Konnte virtuelle Umgebung nicht erstellen.
    pause
    exit /b 1
)
set "PYTHON=%~dp0.venv\Scripts\python.exe"
echo  [OK] Virtuelle Umgebung erstellt.

:HAVE_PYTHON
:: ─── Abhängigkeiten installieren ─────────────────────────
echo.
echo  Installiere Abhängigkeiten (das dauert beim ersten Mal etwas)...
"%PYTHON%" -m pip install --upgrade pip --quiet 2>nul
"%PYTHON%" -m pip install -r "%~dp0requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo  [FEHLER] Installation der Abhängigkeiten fehlgeschlagen.
    echo  Bitte Internetverbindung pruefen und erneut versuchen.
    pause
    exit /b 1
)
echo  [OK] Alle Abhängigkeiten installiert.

:: ─── Desktop-Verknüpfung erstellen ──────────────────────
echo.
echo  Erstelle App-Icon...

set "LOGO_JPG=%~dp0ui\assets\wfv-logo.jpg"
set "ICO_FILE=%~dp0ui\assets\app.ico"

:: Konvertiere JPG → ICO per PowerShell (System.Drawing)
powershell -Command "& { Add-Type -AssemblyName System.Drawing; $img = [System.Drawing.Image]::FromFile('%LOGO_JPG%'); $bmp = New-Object System.Drawing.Bitmap($img, 64, 64); $ms = New-Object System.IO.MemoryStream; $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); $pngBytes = $ms.ToArray(); $ms.Close(); $bmp.Dispose(); $img.Dispose(); $icoStream = New-Object System.IO.FileStream('%ICO_FILE%', [System.IO.FileMode]::Create); $bw = New-Object System.IO.BinaryWriter($icoStream); $bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]1); $bw.Write([byte]64); $bw.Write([byte]64); $bw.Write([byte]0); $bw.Write([byte]0); $bw.Write([UInt16]0); $bw.Write([UInt16]32); $bw.Write([UInt32]$pngBytes.Length); $bw.Write([UInt32]22); $bw.Write($pngBytes); $bw.Close(); $icoStream.Close() }" 2>nul

if exist "%ICO_FILE%" (
    echo  [OK] App-Icon erstellt.
) else (
    echo  [!] Icon-Erstellung fehlgeschlagen (nicht kritisch).
)

echo  Erstelle Desktop-Verknuepfung...

set "SHORTCUT=%USERPROFILE%\Desktop\Spieltagsplaner.lnk"
set "LAUNCHER=%~dp0launcher.pyw"

powershell -Command "& { $ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%~dp0.venv\Scripts\pythonw.exe'; $sc.Arguments = '\"%LAUNCHER%\"'; $sc.WorkingDirectory = '%~dp0'; $sc.Description = 'WFV Spieltagsplaner starten'; $sc.WindowStyle = 1; if (Test-Path '%ICO_FILE%') { $sc.IconLocation = '%ICO_FILE%' }; $sc.Save() }"

if exist "%SHORTCUT%" (
    echo  [OK] Desktop-Verknuepfung "Spieltagsplaner" erstellt.
) else (
    echo  [!] Verknuepfung konnte nicht erstellt werden (nicht kritisch).
)

:: ─── Fertig ──────────────────────────────────────────────
echo.
echo  ══════════════════════════════════════════════════
echo   Installation abgeschlossen!
echo.
echo   Starte den Spieltagsplaner mit:
echo     - Doppelklick auf "Spieltagsplaner" auf dem Desktop
echo     - oder Doppelklick auf "start.bat" in diesem Ordner
echo  ══════════════════════════════════════════════════
echo.
pause
