@echo off
rem Lumina CLI Wrapper for Windows
set SCRIPT_DIR=%~dp0
set PYTHON_BIN=%SCRIPT_DIR%python-dependencies\windows\python.exe

if not exist "%PYTHON_BIN%" set PYTHON_BIN=python

set WIN_SP=%SCRIPT_DIR%python-dependencies\windows\Lib\site-packages
if exist "%WIN_SP%" set PYTHONPATH=%WIN_SP%;%SCRIPT_DIR%scripts;%SCRIPT_DIR%;%PYTHONPATH%

"%PYTHON_BIN%" "%SCRIPT_DIR%Lumina.py" %*
