@echo off
setlocal
title WFV Spieltagsplaner - Installation
color 0F

echo.
echo  ===================================================
echo     WFV Spieltagsplaner - Installation
echo  ===================================================
echo.

:: --- Zielordner ------------------------------------------
set "INSTALL_DIR=%USERPROFILE%\Spieltagsplaner"
set "REPO_ZIP=https://github.com/emirydmr/Spieltagsplanung/archive/refs/heads/marek.zip"
set "ZIP_FILE=%TEMP%\spieltagsplaner.zip"
set "EXTRACT_DIR=%TEMP%\spieltagsplaner_extract"

:: --- Python pruefen --------------------------------------
set "PYTHON_CMD="
where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto :python_ok
)
where python3 >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python3"
    goto :python_ok
)

echo  [!!] Python ist nicht installiert.
echo      Installiere Python 3.13...
echo.

set "PY_INSTALLER=%TEMP%\python-3.13-installer.exe"
echo [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 > "%TEMP%\stp_dlpy.ps1"
echo Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe' -OutFile '%PY_INSTALLER%' -UseBasicParsing >> "%TEMP%\stp_dlpy.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\stp_dlpy.ps1"
del "%TEMP%\stp_dlpy.ps1" 2>nul

if not exist "%PY_INSTALLER%" (
    echo  [X] Python-Download fehlgeschlagen!
    echo      Bitte Python manuell installieren: https://www.python.org
    pause
    exit /b 1
)

echo  Installiere Python (dauert ca. 1-2 Minuten)...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1

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

:python_ok
echo  [OK] Python gefunden
echo.

:: --- Projekt herunterladen --------------------------------
echo  Lade Projekt von GitHub herunter...

if exist "%ZIP_FILE%" del "%ZIP_FILE%"

echo [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 > "%TEMP%\stp_dl.ps1"
echo Invoke-WebRequest -Uri '%REPO_ZIP%' -OutFile '%ZIP_FILE%' -UseBasicParsing >> "%TEMP%\stp_dl.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\stp_dl.ps1"
del "%TEMP%\stp_dl.ps1" 2>nul

if not exist "%ZIP_FILE%" (
    echo  [X] Download fehlgeschlagen! Pruefe die Internetverbindung.
    pause
    exit /b 1
)
echo  [OK] Download abgeschlossen.

:: --- Entpacken -------------------------------------------
echo  Entpacke...

if exist "%EXTRACT_DIR%" rmdir /s /q "%EXTRACT_DIR%"

echo Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force > "%TEMP%\stp_ex.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\stp_ex.ps1"
del "%TEMP%\stp_ex.ps1" 2>nul

set "SRC_DIR=%EXTRACT_DIR%\Spieltagsplanung-marek"

if not exist "%SRC_DIR%" (
    echo  [X] Entpacken fehlgeschlagen!
    pause
    exit /b 1
)

if exist "%INSTALL_DIR%\src\api\server.py" (
    echo  Aktualisiere bestehende Installation...
    robocopy "%SRC_DIR%" "%INSTALL_DIR%" /e /xd .venv output spielplan_logs __pycache__ /xf *.lnk >nul 2>nul
    echo  [OK] Aktualisiert.
) else (
    echo  Erstinstallation...
    if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
    move "%SRC_DIR%" "%INSTALL_DIR%" >nul
    echo  [OK] Projekt installiert.
)

rmdir /s /q "%EXTRACT_DIR%" 2>nul
del "%ZIP_FILE%" 2>nul
echo.

cd /d "%INSTALL_DIR%"

:: --- Virtuelle Umgebung ----------------------------------
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

:: --- Pakete installieren ---------------------------------
echo  Installiere Pakete (dauert beim ersten Mal ca. 2-3 Minuten)...
.venv\Scripts\pip.exe install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo  [X] Paketinstallation fehlgeschlagen!
    pause
    exit /b 1
)
echo  [OK] Alle Pakete installiert.
echo.

:: --- App-Icon erstellen ----------------------------------
set "LOGO_JPG=%INSTALL_DIR%\ui\assets\wfv-logo.jpg"
set "ICO_FILE=%INSTALL_DIR%\ui\assets\app.ico"

if not exist "%ICO_FILE%" (
    echo  Erstelle App-Icon...
    echo Add-Type -AssemblyName System.Drawing > "%TEMP%\stp_icon.ps1"
    echo $img = [System.Drawing.Image]::FromFile('%LOGO_JPG%') >> "%TEMP%\stp_icon.ps1"
    echo $bmp = New-Object System.Drawing.Bitmap($img, 64, 64) >> "%TEMP%\stp_icon.ps1"
    echo $ms = New-Object System.IO.MemoryStream >> "%TEMP%\stp_icon.ps1"
    echo $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png) >> "%TEMP%\stp_icon.ps1"
    echo $pngBytes = $ms.ToArray() >> "%TEMP%\stp_icon.ps1"
    echo $ms.Close(); $bmp.Dispose(); $img.Dispose() >> "%TEMP%\stp_icon.ps1"
    echo $fs = New-Object System.IO.FileStream('%ICO_FILE%', [System.IO.FileMode]::Create) >> "%TEMP%\stp_icon.ps1"
    echo $bw = New-Object System.IO.BinaryWriter($fs) >> "%TEMP%\stp_icon.ps1"
    echo $bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]1) >> "%TEMP%\stp_icon.ps1"
    echo $bw.Write([byte]64); $bw.Write([byte]64); $bw.Write([byte]0); $bw.Write([byte]0) >> "%TEMP%\stp_icon.ps1"
    echo $bw.Write([UInt16]0); $bw.Write([UInt16]32) >> "%TEMP%\stp_icon.ps1"
    echo $bw.Write([UInt32]$pngBytes.Length); $bw.Write([UInt32]22) >> "%TEMP%\stp_icon.ps1"
    echo $bw.Write($pngBytes); $bw.Close(); $fs.Close() >> "%TEMP%\stp_icon.ps1"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\stp_icon.ps1" 2>nul
    del "%TEMP%\stp_icon.ps1" 2>nul
    if exist "%ICO_FILE%" (
        echo  [OK] App-Icon erstellt.
    )
)

:: --- Desktop-Verknuepfung --------------------------------
echo  Erstelle Desktop-Verknuepfung...
set "SHORTCUT=%USERPROFILE%\Desktop\Spieltagsplaner.lnk"
set "LAUNCHER=%INSTALL_DIR%\launcher.pyw"

echo $ws = New-Object -ComObject WScript.Shell > "%TEMP%\stp_lnk.ps1"
echo $sc = $ws.CreateShortcut('%SHORTCUT%') >> "%TEMP%\stp_lnk.ps1"
echo $sc.TargetPath = '%INSTALL_DIR%\.venv\Scripts\pythonw.exe' >> "%TEMP%\stp_lnk.ps1"
echo $sc.Arguments = '"%LAUNCHER%"' >> "%TEMP%\stp_lnk.ps1"
echo $sc.WorkingDirectory = '%INSTALL_DIR%' >> "%TEMP%\stp_lnk.ps1"
echo $sc.Description = 'WFV Spieltagsplaner starten' >> "%TEMP%\stp_lnk.ps1"
echo $sc.WindowStyle = 1 >> "%TEMP%\stp_lnk.ps1"
echo if (Test-Path '%ICO_FILE%') { $sc.IconLocation = '%ICO_FILE%' } >> "%TEMP%\stp_lnk.ps1"
echo $sc.Save() >> "%TEMP%\stp_lnk.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\stp_lnk.ps1"
del "%TEMP%\stp_lnk.ps1" 2>nul

if exist "%SHORTCUT%" (
    echo  [OK] Desktop-Verknuepfung erstellt.
) else (
    echo  [!] Verknuepfung konnte nicht erstellt werden.
)

:: --- Fertig ----------------------------------------------
echo.
echo  ===================================================
echo     Installation abgeschlossen!
echo.
echo     Starte den Spieltagsplaner ueber die
echo     Desktop-Verknuepfung "Spieltagsplaner"
echo  ===================================================
echo.
echo  Installationsordner: %INSTALL_DIR%
echo.

:: Frage ob direkt starten
set /p STARTEN="  Jetzt starten? (j/n): "
if /i "%STARTEN%"=="j" (
    start "" "%INSTALL_DIR%\.venv\Scripts\pythonw.exe" "%LAUNCHER%"
)

pause
