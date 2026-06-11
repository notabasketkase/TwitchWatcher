@echo off
REM ============================================================
REM  Rebuild TwitchWatcher.exe
REM  Just double-click this file whenever you change the code.
REM  The finished exe lands in the "dist" folder.
REM ============================================================

REM Move into this script's own folder so paths work no matter
REM where it's launched from.
cd /d "%~dp0"

echo Building TwitchWatcher.exe ...
echo.

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name TwitchWatcher ^
  --icon "icon.ico" ^
  --add-data "TwitchWatcher_Setup_Guide.pdf;." ^
  --hidden-import plyer.platforms.win.notification ^
  --hidden-import keyring.backends.Windows ^
  "twitch_live_watch.py"

echo.
if exist "dist\TwitchWatcher.exe" (
    echo ============================================================
    echo  DONE!  Your exe is here:  dist\TwitchWatcher.exe
    echo  Share ONLY that .exe with friends -- never a .json file.
    echo ============================================================
) else (
    echo ************************************************************
    echo  BUILD FAILED -- scroll up to see the error.
    echo ************************************************************
)

echo.
pause
