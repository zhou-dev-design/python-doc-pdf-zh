@echo off
rem ============================================================================
rem  Python 中文文档分册 PDF 构建器  --  GUI 启动器
rem
rem  首次运行会自动建 venv 并装 PyQt6 / pypdf，之后直接启动界面。
rem  想把参数传给命令行模式：  启动PDF构建器.bat --cli --from 8
rem
rem  说明：本文件刻意只用 ASCII 字符（批处理 + 中文路径的编码太脆弱），
rem        自己的目录从 %~dp0 取，venv 放在 C:\pypdfbuild 下。
rem ============================================================================
setlocal EnableExtensions
title Python Docs PDF Builder

set "HERE=%~dp0"
set "VENV=C:\pypdfbuild\gui-venv"
set "PY=%VENV%\Scripts\python.exe"
set "PYW=%VENV%\Scripts\pythonw.exe"
set "BOOT=C:\Users\zb137\.workbuddy\binaries\python\versions\3.13.12\python.exe"

if not exist "%PY%" (
  echo [setup] creating virtualenv: %VENV%
  if exist "%BOOT%" (
    "%BOOT%" -m venv "%VENV%"
  ) else (
    py -3 -m venv "%VENV%" 2>nul || python -m venv "%VENV%"
  )
  if not exist "%PY%" goto :err
  echo [setup] installing PyQt6 / pypdf ...
  "%PY%" -m pip install --upgrade pip -q
  "%PY%" -m pip install -q -r "%HERE%requirements.txt"
  if errorlevel 1 goto :err
)

if /i "%~1"=="--cli" goto :cli

start "" "%PYW%" "%HERE%pdf_builder_multi.py"
goto :eof

:cli
"%PY%" "%HERE%pdf_builder_multi.py" %*
goto :eof

:err
echo.
echo [ERROR] setup failed.
echo.
echo   Install Python 3.11+ and try again, or do it by hand:
echo     python -m venv "%VENV%"
echo     "%VENV%\Scripts\python.exe" -m pip install -r "%HERE%requirements.txt"
echo.
pause
