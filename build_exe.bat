@echo off
rem Build a single-file dist\LumEasy.exe (runs tests before and a self-test after).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_exe.ps1"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
