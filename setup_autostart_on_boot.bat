@echo off
TITLE AgriSmart Connect — Add to Windows Startup
COLOR 0B
mode con cols=70 lines=22

:: Must run as Administrator to write to Startup folder
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [ERROR] Please right-click this file and choose
    echo         "Run as administrator" to set up auto-start.
    echo.
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║      AgriSmart Connect  —  Add to Windows Startup              ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.

set "SCRIPT_DIR=%~dp0"
set "TARGET_BAT=%SCRIPT_DIR%start_agrismart.bat"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\AgriSmart Connect.lnk"
set "SHORTCUT_VBS=%TEMP%\CreateAgriSmartShortcut.vbs"

:: ── Write VBScript to create the shortcut ──────────────────────────────
(
    echo Set oWS = WScript.CreateObject("WScript.Shell")
    echo Set oLink = oWS.CreateShortcut("%SHORTCUT_PATH%")
    echo oLink.TargetPath = "cmd.exe"
    echo oLink.Arguments = "/c set AGRISMART_BOOT_WAIT=1 && ""%TARGET_BAT%"""
    echo oLink.WorkingDirectory = "%SCRIPT_DIR%"
    echo oLink.WindowStyle = 1
    echo oLink.Description = "AgriSmart Connect - Smart Farm-to-Market Platform"
    echo oLink.Save
) > "%SHORTCUT_VBS%"

cscript //nologo "%SHORTCUT_VBS%"
del "%SHORTCUT_VBS%"

if exist "%SHORTCUT_PATH%" (
    echo.
    echo  ╔══════════════════════════════════════════════════════════════════╗
    echo  ║  [SUCCESS] AgriSmart added to Windows Startup!                 ║
    echo  ╠══════════════════════════════════════════════════════════════════╣
    echo  ║  Shortcut location:                                             ║
    echo  ║  %STARTUP_FOLDER%\AgriSmart Connect.lnk
    echo  ║                                                                 ║
    echo  ║  Every time you log in to Windows, AgriSmart will:             ║
    echo  ║   • Wait 15s for Windows services to boot                      ║
    echo  ║   • Start PostgreSQL + Ollama                                   ║
    echo  ║   • Apply all migrations                                        ║
    echo  ║   • Launch the web server                                       ║
    echo  ║   • Open your browser to http://localhost:5000                  ║
    echo  ╠══════════════════════════════════════════════════════════════════╣
    echo  ║  To REMOVE auto-start, delete this shortcut:                   ║
    echo  ║  Shell:startup  (type that in Windows Run / Win+R)             ║
    echo  ╚══════════════════════════════════════════════════════════════════╝
    echo.
) else (
    echo  [ERROR] Could not create startup shortcut. Check permissions.
    echo.
)

pause
