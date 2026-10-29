@echo off
rem LumEasy one-click install (source version). Users of the EXE do not need this.
rem Steps and messages are in tools\install.ps1 (kept out of this file: cmd cannot parse UTF-8 text reliably).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install.ps1"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
