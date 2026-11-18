@echo off
setlocal
title NexVerify - Local App
set "APP_DIR=%~dp0"
rem Manus/file-preview may open a temporary copy of this BAT alone.
rem Prefer the complete folder beside the BAT; fall back to this computer's saved bundle.
if not exist "%APP_DIR%runtime\python\python.exe" (
  if exist "C:\Users\saksh\Downloads\NexVerify-tuned\outputs\NexVerify-Ready-To-Run\runtime\python\python.exe" (
    set "APP_DIR=C:\Users\saksh\Downloads\NexVerify-tuned\outputs\NexVerify-Ready-To-Run\"
  )
)
if not exist "%APP_DIR%runtime\python\python.exe" goto missing
if not exist "%APP_DIR%runtime\node\node.exe" goto missing
if not exist "%APP_DIR%launcher.py" goto missing
if not exist "%APP_DIR%frontend\server.js" goto missing
cd /d "%APP_DIR%"
if errorlevel 1 goto missing
echo Using complete folder: %APP_DIR%
"%APP_DIR%runtime\python\python.exe" "%APP_DIR%launcher.py" %*
if errorlevel 1 (
  echo.
  echo Startup failed. Read the message above or data\logs.
  if "%~1"=="" pause
  exit /b 1
)
exit /b 0
:missing
echo.
echo Complete NexVerify folder not found.
echo A BAT file alone cannot run the app. Extract the complete ZIP first.
echo Open that extracted folder and double-click START-NEXVERIFY.bat there.
echo Tried folder: %APP_DIR%
if "%~1"=="" pause
exit /b 1
