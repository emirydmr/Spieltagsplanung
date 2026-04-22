@echo off
chcp 65001 >nul
title Spieltagsplaner – WFV
color 0F

:: ─── Prüfe ob Setup gelaufen ist ─────────────────────────
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo.
    echo  Spieltagsplaner ist noch nicht eingerichtet.
    echo  Starte Ersteinrichtung...
    echo.
    call "%~dp0setup.bat"
    if not exist "%~dp0.venv\Scripts\python.exe" (
        echo  [FEHLER] Setup fehlgeschlagen.
        pause
        exit /b 1
    )
)

set "PYTHON=%~dp0.venv\Scripts\python.exe"

:: ─── Prüfe ob Port 8000 bereits belegt ist ──────────────
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo.
    echo  Spieltagsplaner laeuft bereits!
    echo  Oeffne Browser...
    start http://localhost:8000
    timeout /t 2 /nobreak >nul
    exit /b 0
)

:: ─── Server starten ──────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║      Spieltagsplaner – WFV Bezirk Franken       ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Server wird gestartet...
echo  (Dieses Fenster offen lassen!)
echo.

:: Browser verzögert öffnen (gibt Server Zeit zum Starten)
start /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000/app"

echo  [OK] Browser wird geoeffnet...
echo.
echo  ──────────────────────────────────────────────────
echo   Falls der Browser sich nicht oeffnet:
echo   http://localhost:8000/app im Browser eingeben
echo.
echo   Zum Beenden: Dieses Fenster schliessen
echo   oder Strg+C druecken.
echo  ──────────────────────────────────────────────────
echo.

:: Server im Vordergrund starten (hält Fenster offen)
"%PYTHON%" -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
