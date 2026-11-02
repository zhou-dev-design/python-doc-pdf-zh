@echo off
rem ============================================================================
rem  Package the GUI into a SINGLE standalone exe (PyInstaller / onefile).
rem
rem  This is just a wrapper around build_exe.py. It will:
rem    1. create or reuse the packaging venv  C:\pypdfbuild\exe-venv
rem    2. install PyQt6 / pypdf / PyInstaller into it
rem    3. build  dist\<app name>.exe          <- ONE file, nothing beside it
rem    4. run a smoke test that copies that exe into an EMPTY folder and runs it
rem       there (--tool list / name-map --check / pypdf / GUI start)
rem
rem  Extra options go straight through, e.g.
rem      打包exe.bat --clean --no-smoke
rem      打包exe.bat --onedir           (directory form: starts faster, but the
rem                                      whole folder must be shipped together)
rem      打包exe.bat --console           (keep a console, for debugging)
rem
rem  NOTE: this file is deliberately ASCII-only. Batch + Chinese paths is a
rem        fragile combination, so the Chinese app name lives in build_exe.py
rem        (UTF-8) instead of here.
rem ============================================================================
setlocal EnableExtensions
title Build PDF Builder EXE

set "HERE=%~dp0"
set "BOOT=C:\Users\zb137\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%BOOT%" set "BOOT=py"

"%BOOT%" "%HERE%build_exe.py" %*
set RC=%ERRORLEVEL%

echo.
if "%RC%"=="0" (
  echo [OK] built. Look inside the "dist" folder.
) else (
  echo [FAILED] exit code %RC%
)
pause
