@echo off
rem Lumina CLI Wrapper for Windows
set SCRIPT_DIR=%~dp0
set PYTHON_BIN=%SCRIPT_DIR%python-dependencies\windows\python.exe

if not exist "%PYTHON_BIN%" set PYTHON_BIN=python

"%PYTHON_BIN%" "%SCRIPT_DIR%Lumina.py" %*
