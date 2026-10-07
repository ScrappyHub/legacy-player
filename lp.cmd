@echo off
rem Lets you type  lp install  in cmd.exe or PowerShell from this folder.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lp.ps1" %*
