@echo off
setlocal enabledelayedexpansion
title Salary Planner - One-Click Install

:: ────────────────────────────────────────────────
::  Portable Mode Detection
::  If run from inside the SalaryPlanner folder,
::  just launch the app without installing.
:: ────────────────────────────────────────────────
if exist "%~dp0SalaryPlanner.exe" (
    echo [portable] Running directly from folder...
    cd /d "%~dp0"
    start "" "%~dp0SalaryPlanner.exe"
    exit /b 0
)

:: ────────────────────────────────────────────────
::  Installer Mode
:: ────────────────────────────────────────────────
set "APP_NAME=Salary Planner"
set "INSTALL_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "SOURCE_DIR=%~dp0"

echo.
echo ╔══════════════════════════════════════════════╗
echo ║   Salary Planner Installer                    ║
echo ║   月度工资计划器                               ║
echo ╚══════════════════════════════════════════════╝
echo.
echo This will install the app to:
echo   %INSTALL_DIR%
echo.

choice /C YN /M "Continue with installation"
if errorlevel 2 exit /b 0

:: Remove previous install
if exist "%INSTALL_DIR%" (
    echo Removing previous installation...
    taskkill /f /im SalaryPlanner.exe 2>nul
    rmdir /S /Q "%INSTALL_DIR%" 2>nul
)

:: Create directories
echo [1/3] Copying files...
mkdir "%INSTALL_DIR%" 2>nul
xcopy /E /I /Y "%SOURCE_DIR%SalaryPlanner\*" "%INSTALL_DIR%" >nul
if %errorlevel% neq 0 (
    echo [ERROR] Failed to copy files from %SOURCE_DIR%SalaryPlanner\
    echo Make sure you extracted the entire ZIP file.
    pause
    exit /b 1
)
echo       Done.

:: Create Shortcuts
echo [2/3] Creating shortcuts...

:: Start Menu
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\%APP_NAME%"
mkdir "%START_MENU%" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%START_MENU%\%APP_NAME%.lnk'); $s.TargetPath = '%INSTALL_DIR%\SalaryPlanner.exe'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Monthly Salary Planner - 月度工资计划器'; $s.Save()"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%START_MENU%\Uninstall.lnk'); $s.TargetPath = '%INSTALL_DIR%\uninstall.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Uninstall Salary Planner'; $s.Save()"

:: Desktop shortcut
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\%APP_NAME%.lnk'); $s.TargetPath = '%INSTALL_DIR%\SalaryPlanner.exe'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Monthly Salary Planner - 月度工资计划器'; $s.Save()"

echo       Done.

:: Create uninstaller
echo [3/3] Creating uninstaller...
(
echo @echo off
echo echo Uninstalling Salary Planner...
echo taskkill /f /im SalaryPlanner.exe 2^>nul
echo rmdir /S /Q "%INSTALL_DIR%" 2^>nul
echo del /Q "%START_MENU%\*.lnk" 2^>nul
echo rmdir "%START_MENU%" 2^>nul
echo del /Q "%%USERPROFILE%%\Desktop\Salary Planner.lnk" 2^>nul
echo echo.
echo echo Salary Planner has been uninstalled.
echo echo Your data files in %%LOCALAPPDATA%%\Salary Planner\data\ have been removed.
echo pause
) > "%INSTALL_DIR%\uninstall.bat"
echo       Done.

:: Done
echo.
echo ╔══════════════════════════════════════════════╗
echo ║  Ready!                                       ║
echo ║                                              ║
echo ║  Start Menu → Salary Planner                  ║
echo ║  Desktop → Salary Planner                     ║
echo ╚══════════════════════════════════════════════╝
echo.

choice /C YN /M "Launch now"
if errorlevel 2 goto :end
start "" "%INSTALL_DIR%\SalaryPlanner.exe"

:end
pause
