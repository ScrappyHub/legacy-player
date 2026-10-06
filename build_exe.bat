@echo off
rem Builds dist\LegacyPlayer.exe (one file, no Python needed to run it).
rem Needs Python 3.13 or newer from python.org (tick "Add to PATH"). Run this from the repo folder.
setlocal
cd /d "%~dp0"
python --version || (echo Python was not found. Install Python 3.13+ from python.org and try again. & exit /b 1)
python -m pip install --upgrade pip pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --name LegacyPlayer ^
  --paths . ^
  --add-data "launcher\ui;launcher\ui" ^
  --collect-submodules launcher --collect-submodules server ^
  --collect-submodules adapters --collect-submodules runtime --collect-submodules frontend ^
  legacy_player_app.py || exit /b 1
echo.
echo Built: %CD%\dist\LegacyPlayer.exe
echo Double-click it to open Legacy Player. Your data lives in %USERPROFILE%\.legacy-player
endlocal
