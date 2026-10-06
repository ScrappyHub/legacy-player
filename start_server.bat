@echo off
rem Starts the multiplayer server in the background. Use stop_server.bat to stop it.
cd /d "%~dp0"
python -m server.cli start --detach
pause
